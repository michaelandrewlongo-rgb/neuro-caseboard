"""Executive-Navy case-board PDF — render a Dossier to a print-grade PDF that matches the
redesigned Streamlit console (`app/signal_theme.py`).

Where ``render_pdf.py`` (fpdf2) emits a plain light clinical document and ``briefing_pdf.py``
emits the *old* dark Signal briefing for Q&A, this renders the **build dossier** in the current
Executive-Navy identity: a deep-navy masthead over a bright report plane, the three-font role
system (Archivo UI / Source Serif 4 reading column / IBM Plex Mono micro-labels), one deep-teal
accent, an evidence-mix proportion bar + stat cards + legend, and status-marker claim cards with
indented ``Why:`` rationale. HTML → PDF via Playwright/Chromium.

``build_caseboard_html`` is pure and dependency-light (testable offline). ``render_caseboard_pdf``
needs the ``briefing`` extra (Playwright + a Chromium binary).
"""
from __future__ import annotations

import datetime as dt
import html

from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, inline, img_data_uri
from neuro_caseboard.model import Dossier

_STATUS_LABEL = {"supported": "Corpus-supported", "verify": "To verify"}

# Standing confidentiality / clinician-verify banner (LOOP_PROMPT §6). position:fixed repeats it on
# every printed page in Chromium; the bottom padding on .content keeps body text clear of it.
VERIFY_BANNER = ("Confidential — clinical decision support only; "
                 "the surgeon verifies every recommendation.")
_CASE_EXTRA_CSS = """
.verify-banner{ position:fixed; bottom:0; left:0; right:0; padding:3px 14mm;
  font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.02em; color:#000;
  background:var(--yellow); border-top:2px solid #000; text-align:center; }
.content{ padding-bottom:14mm; }
.litblock{ margin:3mm 0 1mm; border:2px solid #000; border-left:5px solid var(--blue);
  padding:3mm 4mm; box-shadow:3px 3px 0 0 #000; }
.litblock .lh{ font-family:var(--ui); font-weight:700; font-size:9.5pt; color:var(--blue);
  letter-spacing:.02em; text-transform:uppercase; }
.litblock .ln{ font-family:var(--read); font-size:9.6pt; color:#000; margin:1mm 0; }
.litblock .lc{ font-family:var(--read); font-size:8.6pt; color:var(--muted); padding:.6mm 0; }
.litblock .lc .k{ font-family:var(--mono); font-size:7pt; font-weight:700; color:var(--blue); margin-right:2mm; }
.litblock a{ color:var(--blue); text-decoration:none; }
"""


def _literature_html(lit) -> str:
    """The contemporary-literature block ([L#] axis), separate from the corpus markers (WS-3)."""
    if not lit or not getattr(lit, "narrative", ""):
        return ""
    rows = []
    for c in getattr(lit, "citations", []) or []:
        link = f"https://doi.org/{c.doi}" if getattr(c, "doi", "") else getattr(c, "url", "")
        meta = ", ".join(p for p in (html.escape(c.journal or ""), str(c.year or "")) if p)
        a = f' · <a href="{html.escape(link)}">link</a>' if link else ""
        rows.append(f'<div class="lc"><span class="k">[L{c.n}]</span>{html.escape(c.title or "")}'
                    f'{(" — " + meta) if meta else ""}{a}</div>')
    return ('<div class="litblock"><div class="lh">Contemporary Literature</div>'
            f'<div class="ln">{inline(lit.narrative)}</div>{"".join(rows)}</div>')


def _evidence_bar(s) -> str:
    total = max(s.supported + s.to_verify + s.quarantined, 1)
    seg = lambda n, var: (f'<span style="width:{n / total * 100:.1f}%;background:{var}"></span>' if n else "")
    return ('<div class="evbar">' + seg(s.supported, "var(--supported)")
            + seg(s.to_verify, "var(--verify)") + seg(s.quarantined, "var(--quar)") + "</div>")


def _claim_html(c) -> str:
    status = c.status if c.status in _STATUS_LABEL else "supported"
    figref = ""
    if c.figure_ids:
        figref = ' <span class="figref">see ' + ", ".join(f"Fig {html.escape(f)}" for f in c.figure_ids) + "</span>"
    parts = [f'<div class="claim {status}">',
             f'<span class="marker {status}">{_STATUS_LABEL[status]}</span>',
             f'<div class="ctext">{inline(c.text)}{figref}</div>']
    if c.why:
        parts.append(f'<div class="why"><b>Why</b>{inline(c.why)}</div>')
    if c.sub_items:
        parts.append('<ul class="subs">' + "".join(f"<li>{inline(i)}</li>" for i in c.sub_items) + "</ul>")
    parts.append("</div>")
    return "".join(parts)


def _figure_html(fig) -> str:
    try:
        img = f'<img src="{img_data_uri(fig.image_path)}">'
    except Exception:
        img = ""  # never emit a broken image; keep the caption
    cite = f' <span class="cite">— {html.escape(fig.citation)}</span>' if fig.citation else ""
    rel = f'<span class="rel">{inline(fig.relevance)}</span>' if fig.relevance else ""
    return (f'<figure>{img}<figcaption><span class="fid">Fig {html.escape(fig.fig_id)}</span>'
            f'{inline(fig.caption)}{cite}{rel}</figcaption></figure>')


def build_caseboard_html(dossier: Dossier, *, subtitle: str = "", today: str | None = None) -> str:
    """Pure: render a Dossier to an Executive-Navy HTML string (figures whose file can't be read
    are kept caption-only, never crash)."""
    today = today or dt.date.today().isoformat()
    s = dossier.summary
    keys = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

    out = [
        "<!doctype html><html><head><meta charset='utf-8'><style>",
        EXEC_NAVY_CSS, _CASE_EXTRA_CSS, "</style></head><body>",
        f'<div class="verify-banner">{html.escape(VERIFY_BANNER)}</div>',
        '<div class="masthead"><div class="mh-brand"><span class="sq"></span>NEURO·CASEBOARD</div>',
        '<div class="mh-eyebrow">Neurosurgery Signal · pre-operative dossier</div></div>',
        '<div class="content">',
        '<span class="eyebrow">Build · Pre-op dossier</span>',
        f'<h1 class="title">{html.escape(dossier.title)}</h1>',
    ]
    if subtitle:
        out.append(f'<div class="standfirst">{html.escape(subtitle)}</div>')
    out.append('<div class="rule"></div>')
    out.append(_evidence_bar(s))
    out.append(
        '<div class="metrics">'
        f'<div class="metric"><div class="v">{len(dossier.sections)}</div><div class="k">Sections</div></div>'
        f'<div class="metric supported"><div class="v">{s.supported}</div><div class="k">Corpus-supported</div></div>'
        f'<div class="metric verify"><div class="v">{s.to_verify}</div><div class="k">To verify</div></div>'
        f'<div class="metric quar"><div class="v">{s.quarantined}</div><div class="k">Quarantined</div></div>'
        '</div>')
    out.append(
        '<div class="legend">'
        '<div class="item"><span class="sw" style="background:var(--supported)"></span>Corpus-supported</div>'
        '<div class="item"><span class="sw" style="background:var(--verify)"></span>To verify</div>'
        '<div class="item"><span class="sw" style="background:var(--quar)"></span>Quarantined (appendix)</div>'
        '</div>')

    seen: set[str] = set()
    for i, sec in enumerate(dossier.sections):
        k = keys[i] if i < len(keys) else str(i + 1)
        out.append('<div class="section">'
                   f'<div class="sec-h"><span class="k">{k}</span>'
                   f'<span class="t">{html.escape(sec.heading)}</span><span class="ln"></span></div>')
        if sec.intro:
            out.append(f'<div class="sec-intro">{inline(sec.intro)}</div>')
        for c in sec.claims:
            out.append(_claim_html(c))
        for fig in sec.figures:
            if fig.image_path in seen:
                continue
            seen.add(fig.image_path)
            out.append(_figure_html(fig))
        out.append(_literature_html(getattr(sec, "literature", None)))
        for ref in sec.cross_refs:
            out.append(f'<div class="xnote">{inline(ref)}</div>')
        out.append("</div>")

    if not dossier.appendix.is_empty():
        out.append('<div class="appendix"><div class="sec-h"><span class="k">APX</span>'
                   '<span class="t">Appendix — evidence sources & off-target claims</span>'
                   '<span class="ln"></span></div>')
        for e in dossier.appendix.entries:
            out.append(f'<div class="ap-h">{html.escape(e.heading)}</div><ul>')
            for it in e.items:
                out.append(f"<li>{inline(it)}</li>")
            for sr in e.sources:
                out.append(f"<li>{inline(sr)}</li>")
            out.append("</ul>")
        out.append("</div>")

    out.append("</div>")  # /content
    out.append(f'<div class="footer">Generated from the neurosurgery textbook corpus · '
               f'decision-support only · {html.escape(today)}</div>')
    out.append("</body></html>")
    return "".join(out)


def render_caseboard_pdf(dossier: Dossier, out_path, *, subtitle: str = "") -> str:
    """Render the dossier to an A4 PDF at ``out_path`` via Playwright/Chromium. Requires the
    ``briefing`` optional dependency and an installed Chromium binary."""
    from playwright.sync_api import sync_playwright
    doc = build_caseboard_html(dossier, subtitle=subtitle)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(doc, wait_until="networkidle")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.pdf(path=str(out_path), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    return str(out_path)
