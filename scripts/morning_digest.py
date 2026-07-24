#!/usr/bin/env python3
"""Morning rounds digest: overnight PubMed surveillance -> one cited email.

Runs on the VM *host* (not inside the caseboard container) from cron. Deliberately
stdlib-only so it needs no venv, no image rebuild, and no container restart — it cannot
touch the running server's memory. It talks to PubMed E-utilities, OpenRouter, and SMTP
over the network and nothing else.

    python3 morning_digest.py --dry-run --out /tmp/digest.html   # build, don't send
    python3 morning_digest.py                                    # build and email

Topics file: one PubMed query per line, blank lines and #-comments ignored. An optional
"Label :: query" form gives the section a friendlier heading than the raw query.

State lives in a SQLite table of PMIDs already reported, so a paper is emailed once even
when PubMed backfills its entry date. Papers are marked seen ONLY after the email is
accepted by the SMTP server — a failed send never silently swallows a day's literature.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import os
import re
import smtplib
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Mirrors WOVEN_EXTRACT_RULES in neuro_caseboard/woven_synth.py. Duplicated rather than
# imported: this script is stdlib-only by design so it can run on the host without the
# package installed. ponytail: if the two drift, the repo's copy is authoritative.
DIGEST_SYSTEM = (
    "You are a neurosurgical evidence summarizer. Using ONLY the numbered studies "
    "provided, report what is new.\n"
    "- Answer as a flat list of bullet points ('- ' at the start of each line). No "
    "preamble, no closing summary, no headings.\n"
    "- Each bullet states ONE finding from the studies and ends with its citation "
    "marker, e.g. [L2]. A bullet with no citable source does not belong in the answer.\n"
    "- Report only what the studies state. Do not add background knowledge, inference, "
    "or recommendations of your own.\n"
    "- Keep each bullet to one sentence, in the studies' own terms (their thresholds, "
    "units, and qualifiers verbatim where possible).\n"
    "- Lead with the bullets that would change management; omit purely incremental "
    "findings rather than padding.\n"
    "- If studies disagree, give each view its own bullet with its own citation."
)


# --- PubMed ---------------------------------------------------------------------------

def window_term(topic: str, since: _dt.date) -> str:
    """Restrict a topic query to records that ENTERED PubMed on/after `since`.

    [EDAT] (entry date) rather than [PDAT] (publication date): a paper published months
    ago but indexed last night is still new *to us*, and PDAT would miss it forever.
    """
    return f'({topic}) AND ("{since:%Y/%m/%d}"[EDAT] : "3000"[EDAT])'


def _get(url: str, params: dict, *, api_key: str = "", retries: int = 3):
    if api_key:
        params = {**params, "api_key": api_key}
    qs = urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": "neuro-caseboard-digest/1"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:            # 429/5xx are transient at NCBI
            last = exc
            if exc.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"NCBI request failed: {last}")


def esearch(term: str, *, api_key: str = "", retmax: int = 40) -> list[str]:
    import xml.etree.ElementTree as ET
    text = _get(f"{EUTILS}/esearch.fcgi",
                {"db": "pubmed", "term": term, "retmax": str(retmax),
                 "retmode": "xml", "sort": "date"}, api_key=api_key)
    root = ET.fromstring(text)
    return [e.text or "" for e in root.findall(".//Id") if e.text]


def esummary(pmids: list[str], *, api_key: str = "") -> list[dict]:
    if not pmids:
        return []
    text = _get(f"{EUTILS}/esummary.fcgi",
                {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}, api_key=api_key)
    data = json.loads(text).get("result", {})
    out = []
    for pmid in pmids:                                   # preserve PubMed's date order
        a = data.get(pmid) or {}
        if not a.get("uid"):
            continue
        authors = [x.get("name", "") for x in a.get("authors", []) if x.get("name")]
        if len(authors) > 3:
            authors = authors[:3] + ["et al."]
        out.append({
            "pmid": a["uid"],
            "title": (a.get("title") or "").strip().rstrip("."),
            "journal": a.get("source", ""),
            "pubdate": a.get("pubdate", ""),
            "authors": ", ".join(authors),
            "pub_types": a.get("pubtype") or [],
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{a['uid']}/",
        })
    return out


def efetch_abstracts(pmids: list[str], *, api_key: str = "") -> dict[str, str]:
    import xml.etree.ElementTree as ET
    if not pmids:
        return {}
    text = _get(f"{EUTILS}/efetch.fcgi",
                {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml",
                 "rettype": "abstract"}, api_key=api_key)
    root = ET.fromstring(text)
    out: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        parts = []
        for at in article.findall(".//Abstract/AbstractText"):
            label = (at.get("Label") or "").strip().rstrip(":")
            body = "".join(at.itertext()).strip()
            if body:
                parts.append(f"{label}: {body}" if label else body)
        if parts:
            out[pmid_el.text] = " ".join(parts)
    return out


# --- seen-state -----------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
  topic TEXT NOT NULL, pmid TEXT NOT NULL, ts INTEGER NOT NULL,
  PRIMARY KEY (topic, pmid)
)"""


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def unseen(conn: sqlite3.Connection, topic: str, pmids: list[str]) -> list[str]:
    if not pmids:
        return []
    marks = ",".join("?" * len(pmids))
    known = {r[0] for r in conn.execute(
        f"SELECT pmid FROM seen WHERE topic=? AND pmid IN ({marks})", [topic, *pmids])}
    return [p for p in pmids if p not in known]


def mark_seen(conn: sqlite3.Connection, topic: str, pmids: list[str]) -> None:
    now = int(time.time())
    conn.executemany("INSERT OR IGNORE INTO seen (topic, pmid, ts) VALUES (?,?,?)",
                     [(topic, p, now) for p in pmids])
    conn.commit()


# --- topics ---------------------------------------------------------------------------

def load_topics(path: str) -> list[tuple[str, str]]:
    """-> [(label, query)]. 'Label :: query' sets a heading; otherwise the query is both."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            label, sep, query = line.partition("::")
            if sep:
                out.append((label.strip(), query.strip()))
            else:
                out.append((line, line))
    return out


# --- synthesis ------------------------------------------------------------------------

def _format_studies(papers: list[dict]) -> str:
    blocks = []
    for i, p in enumerate(papers, 1):
        blocks.append(f"[L{i}] {p['title']} — {p['journal']} {p['pubdate']} "
                      f"(PMID {p['pmid']})\n{p.get('abstract', '')}")
    return "\n\n".join(blocks)


def summarize(topic: str, papers: list[dict], *, api_key: str, model: str) -> str:
    """Cited bullets over the new abstracts. Returns '' if the model is unusable — the
    caller still lists the papers, so a synthesis outage degrades the email, not loses it."""
    if not papers:
        return ""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": DIGEST_SYSTEM},
                     {"role": "user",
                      "content": f"Topic: {topic}\n\nStudies:\n{_format_studies(papers)}"}],
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:                              # fail loud, keep the papers
        print(f"  ! synthesis failed for {topic!r}: {exc}", file=sys.stderr)
        return ""


# --- rendering ------------------------------------------------------------------------

_CITE = re.compile(r"\[L(\d+)\]")


def _link_citations(text: str, papers: list[dict]) -> str:
    """Turn [L3] into a link to that paper on PubMed. Escapes first, so titles and model
    output can never inject markup."""
    esc = html.escape(text)

    def repl(m):
        idx = int(m.group(1))
        if 1 <= idx <= len(papers):
            return (f'<a href="{html.escape(papers[idx - 1]["url"])}" '
                    f'style="color:#c8102e;text-decoration:none">[L{idx}]</a>')
        return m.group(0)
    return _CITE.sub(repl, esc)


def render_html(sections: list[dict], *, since: _dt.date, generated: _dt.datetime) -> str:
    # ponytail: inline styles, no <style> block — Gmail strips most head CSS. Light only.
    css_b = "font:15px/1.55 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1a1a"
    parts = [
        f'<div style="max-width:680px;margin:0 auto;padding:24px;{css_b}">',
        '<div style="border-bottom:3px solid #c8102e;padding-bottom:10px;margin-bottom:22px">',
        '<div style="font-size:20px;font-weight:700;letter-spacing:-.01em">Morning Rounds</div>',
        f'<div style="font-size:13px;color:#666;margin-top:3px">New on PubMed since '
        f'{since:%b %-d} &middot; generated {generated:%a %b %-d, %-I:%M %p}</div></div>',
    ]
    total = sum(len(s["papers"]) for s in sections)
    if not total:
        parts.append('<p style="color:#666">No new papers matched your topics since '
                     f'{since:%b %-d}. ({len(sections)} topics watched.)</p>')
    for s in sections:
        parts.append(f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                     f'letter-spacing:.08em;color:#c8102e;margin:26px 0 8px">'
                     f'{html.escape(s["label"])}</div>')
        if not s["papers"]:
            parts.append('<div style="color:#999;font-size:14px">nothing new</div>')
            continue
        if s["bullets"]:
            items = [ln.strip()[2:].strip() for ln in s["bullets"].splitlines()
                     if ln.strip().startswith("- ")]
            if items:
                parts.append('<ul style="margin:0 0 14px;padding-left:20px">')
                parts += [f'<li style="margin-bottom:7px">{_link_citations(i, s["papers"])}</li>'
                          for i in items]
                parts.append("</ul>")
        else:
            parts.append('<div style="color:#a00;font-size:13px;margin-bottom:10px">'
                         'Summary unavailable — papers listed below.</div>')
        parts.append('<div style="border-top:1px solid #e6e6e6;padding-top:10px">')
        for i, p in enumerate(s["papers"], 1):
            pt = next((t for t in p.get("pub_types", [])
                       if t in ("Randomized Controlled Trial", "Meta-Analysis",
                                "Systematic Review", "Practice Guideline")), "")
            badge = (f'<span style="background:#ffe9ec;color:#c8102e;font-size:10px;'
                     f'padding:1px 5px;border-radius:3px;margin-left:5px">'
                     f'{html.escape(pt)}</span>') if pt else ""
            parts.append(
                f'<div style="margin-bottom:9px;font-size:13px;line-height:1.45">'
                f'<span style="color:#999">[L{i}]</span> '
                f'<a href="{html.escape(p["url"])}" style="color:#1a1a1a;font-weight:600;'
                f'text-decoration:none">{html.escape(p["title"])}</a>{badge}<br>'
                f'<span style="color:#777">{html.escape(p["authors"])} &middot; '
                f'<i>{html.escape(p["journal"])}</i> {html.escape(p["pubdate"])}</span></div>')
        parts.append("</div>")
        if s.get("dropped"):
            parts.append(f'<div style="color:#999;font-size:12px">+{s["dropped"]} more new '
                         f'paper(s) not shown (per-topic cap).</div>')
    parts.append('<div style="margin-top:28px;border-top:1px solid #e6e6e6;padding-top:10px;'
                 'color:#999;font-size:11px">neuro-caseboard &middot; summaries are generated '
                 'from the abstracts above and are decision-support, not clinical judgment.'
                 '</div></div>')
    return "\n".join(parts)


def render_text(sections: list[dict], *, since: _dt.date) -> str:
    lines = [f"MORNING ROUNDS — new on PubMed since {since:%b %d}", ""]
    if not sum(len(s["papers"]) for s in sections):
        lines.append(f"No new papers matched your topics. ({len(sections)} topics watched.)")
    for s in sections:
        lines += [s["label"].upper(), ""]
        if not s["papers"]:
            lines += ["  nothing new", ""]
            continue
        if s["bullets"]:
            lines += [f"  {ln.strip()}" for ln in s["bullets"].splitlines() if ln.strip()]
            lines.append("")
        for i, p in enumerate(s["papers"], 1):
            lines += [f"  [L{i}] {p['title']}",
                      f"       {p['journal']} {p['pubdate']} — {p['url']}"]
        lines.append("")
    return "\n".join(lines)


# --- delivery -------------------------------------------------------------------------

def send_email(*, host: str, port: int, user: str, password: str, sender: str,
               to: list[str], subject: str, text: str, html_body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.starttls(context=ssl.create_default_context())   # 587; 465 is blocked here
        smtp.login(user, password)
        smtp.send_message(msg)


# --- orchestration --------------------------------------------------------------------

def build_sections(topics, conn, *, days: int, max_per_topic: int, ncbi_key: str,
                   or_key: str, model: str, today: _dt.date | None = None) -> list[dict]:
    since = (today or _dt.date.today()) - _dt.timedelta(days=days)
    sections = []
    for label, query in topics:
        pmids = esearch(window_term(query, since), api_key=ncbi_key)
        fresh = unseen(conn, query, pmids)
        dropped = max(0, len(fresh) - max_per_topic)
        if dropped:                                       # no silent truncation
            print(f"  {label}: {len(fresh)} new, showing {max_per_topic}", file=sys.stderr)
        keep = fresh[:max_per_topic]
        papers = esummary(keep, api_key=ncbi_key)
        abstracts = efetch_abstracts([p["pmid"] for p in papers], api_key=ncbi_key)
        papers = [p for p in papers if abstracts.get(p["pmid"])]   # no abstract -> nothing to cite
        for p in papers:
            p["abstract"] = abstracts[p["pmid"]]
        bullets = summarize(label, papers, api_key=or_key, model=model) if papers else ""
        sections.append({"label": label, "query": query, "papers": papers,
                         "bullets": bullets, "dropped": dropped,
                         # every PMID we looked at is marked, so a paper whose abstract we
                         # skipped is not re-fetched forever
                         "reported": keep})
        print(f"  {label}: {len(pmids)} hits, {len(fresh)} new, {len(papers)} with abstracts",
              file=sys.stderr)
        time.sleep(0.2)                                   # stay under NCBI's rate cap
    return sections


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topics", default=os.environ.get("DIGEST_TOPICS", "/opt/caseboard/digest_topics.txt"))
    ap.add_argument("--db", default=os.environ.get("DIGEST_DB", "/opt/caseboard/digest.db"))
    ap.add_argument("--days", type=int, default=int(os.environ.get("DIGEST_DAYS", "7")))
    ap.add_argument("--max-per-topic", type=int, default=int(os.environ.get("DIGEST_MAX", "6")))
    ap.add_argument("--dry-run", action="store_true", help="build but do not send or mark seen")
    ap.add_argument("--out", default="", help="also write the HTML here")
    args = ap.parse_args(argv)

    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not or_key:
        print("FATAL: OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 2
    topics = load_topics(args.topics)
    if not topics:
        print(f"FATAL: no topics in {args.topics}", file=sys.stderr)
        return 2
    # Check delivery BEFORE the work: retrieval + synthesis costs ~3 min and one LLM call
    # per topic, and discovering a missing password afterwards wastes all of it.
    to = [x.strip() for x in os.environ.get("DIGEST_TO", "").split(",") if x.strip()]
    user = os.environ.get("DIGEST_SMTP_USER", "")
    password = os.environ.get("DIGEST_SMTP_PASS", "")
    if not args.dry_run and not (to and user and password):
        print("FATAL: DIGEST_TO / DIGEST_SMTP_USER / DIGEST_SMTP_PASS must all be set",
              file=sys.stderr)
        return 2

    conn = open_db(args.db)
    since = _dt.date.today() - _dt.timedelta(days=args.days)
    print(f"digest: {len(topics)} topics, window since {since:%Y-%m-%d}", file=sys.stderr)
    sections = build_sections(topics, conn, days=args.days,
                              max_per_topic=args.max_per_topic,
                              ncbi_key=os.environ.get("NCBI_API_KEY", ""),
                              or_key=or_key,
                              model=os.environ.get("OPENROUTER_MODEL", "z-ai/glm-5.2"))
    n_new = sum(len(s["papers"]) for s in sections)
    html_body = render_html(sections, since=since, generated=_dt.datetime.now())
    text = render_text(sections, since=since)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(html_body)
        print(f"wrote {args.out} ({len(html_body)} bytes)", file=sys.stderr)

    if args.dry_run:
        print(f"dry-run: {n_new} new paper(s); nothing sent, nothing marked seen",
              file=sys.stderr)
        return 0

    subject = (f"Morning Rounds — {n_new} new paper{'s' if n_new != 1 else ''}"
               if n_new else "Morning Rounds — nothing new")
    send_email(host=os.environ.get("DIGEST_SMTP_HOST", "smtp.gmail.com"),
               port=int(os.environ.get("DIGEST_SMTP_PORT", "587")),
               user=user, password=password,
               sender=os.environ.get("DIGEST_FROM", user), to=to,
               subject=subject, text=text, html_body=html_body)
    # Only now: delivery succeeded, so these papers are genuinely reported.
    for s in sections:
        mark_seen(conn, s["query"], s["reported"])
    print(f"sent to {', '.join(to)} ({n_new} new)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
