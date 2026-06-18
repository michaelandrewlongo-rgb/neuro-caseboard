"""Executive-Navy briefing PDF for Q&A (ask) results -- the print sibling of caseboard_pdf.py
for the question-answer shape.

Renders a query result (markdown answer + numbered textbook citations + optional contemporary
PubMed literature + figures) in the current Executive-Navy identity (shared with the web console
and the build dossier via exec_navy.py): a deep-navy masthead over a bright report plane, the
three-font role system (Archivo UI / Source Serif 4 reading column / IBM Plex Mono micro-labels)
and one deep-teal accent.

``build_briefing_html`` is pure and dependency-light (unit-tested offline). ``render_briefing_pdf``
needs the ``briefing`` extra (Playwright + a Chromium binary).
"""
from __future__ import annotations

import datetime as dt
import html
import re

from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, img_data_uri

DEFAULT_EYEBROW = "Ask · Citation-grounded"

# Q&A-only selectors layered on the shared Executive-Navy sheet (masthead, eyebrow chip, title,
# rule, section headers, figures and footer all come from EXEC_NAVY_CSS).
ASK_CSS = """
.answer{ font-family:var(--read); font-size:11pt; line-height:1.55; color:#000; max-width:165mm; }
.answer p{ margin:0 0 2.6mm; }
.answer ul{ margin:0 0 3mm; padding-left:6mm; } .answer li{ margin:0 0 1.2mm; }
.answer strong{ color:#000; font-weight:700; }
.answer h2{ font-family:var(--ui); font-weight:700; font-size:13pt; color:#000;
  letter-spacing:-.01em; margin:6mm 0 2mm; padding-top:3mm; border-top:2px solid #000; }
.answer h3{ font-family:var(--ui); font-weight:700; font-size:10.5pt; color:var(--accent);
  margin:4mm 0 1.5mm; }
.sources{ border:2px solid #000; border-radius:0; padding:1mm 4mm; max-width:165mm;
  box-shadow:3px 3px 0 0 #000; }
.src{ font-family:var(--read); font-size:9.6pt; color:#000; padding:1.8mm 0;
  border-top:2px solid #000; }
.src:first-child{ border-top:none; }
.src .n, .src .ln{ font-family:var(--mono); font-size:7pt; color:var(--accent); font-weight:700;
  margin-right:2mm; }
.src a{ color:var(--accent); text-decoration:none; }
.litmeta{ color:var(--muted); }
"""


def _g(obj, key, default=None):
    """Read ``key`` from a dict or an attribute-bearing object (duck-typed result/citation/figure)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _fmt(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(s))


def _md_to_html(md: str) -> str:
    out, in_ul = [], False

    def close():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>"); in_ul = False

    for raw in (md or "").split("\n"):
        s = raw.strip()
        if not s:
            close(); continue
        if s.startswith("### "):
            close(); out.append(f"<h3>{_fmt(s[4:])}</h3>"); continue
        if s.startswith("## "):
            close(); out.append(f"<h2>{_fmt(s[3:])}</h2>"); continue
        if s[:2] in ("* ", "- ") or s.startswith("*\t"):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{_fmt(s[1:].strip())}</li>"); continue
        close(); out.append(f"<p>{_fmt(s)}</p>")
    close()
    return "\n".join(out)


def _sources_html(result) -> str:
    rows = []
    for c in (_g(result, "citations") or []):
        loc = html.escape(_g(c, "book") or "")
        if _g(c, "chapter"):
            loc += f", {html.escape(_g(c, 'chapter'))}"
        loc += f", p.{_g(c, 'page')}"
        rows.append(f'<div class="src"><span class="n">[{_g(c, "n")}]</span> {loc}</div>')
    return ('<div class="section"><div class="sec-h"><span class="k">SRC</span>'
            '<span class="t">Sources</span><span class="ln"></span></div>'
            f'<div class="sources">{"".join(rows)}</div></div>')


def _literature_html(result) -> str:
    """Render the Contemporary Literature section, or '' when absent/empty."""
    lit = _g(result, "literature")
    if not lit:
        return ""
    narrative = _g(lit, "narrative") or ""
    cites = _g(lit, "citations") or []
    if not narrative or not cites:
        return ""
    rows = []
    for c in cites:
        doi = _g(c, "doi") or ""
        href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
        meta = ", ".join(p for p in (html.escape(_g(c, "journal") or ""),
                                     str(_g(c, "year") or "")) if p)
        link = f' · <a href="{html.escape(href)}">link</a>' if href else ""
        rows.append(f'<div class="src"><span class="ln">[L{_g(c, "n")}]</span> '
                    f'{html.escape(_g(c, "title") or "")} '
                    f'<span class="litmeta">— {meta}</span>{link}</div>')
    return ('<div class="section"><div class="sec-h"><span class="k">LIT</span>'
            '<span class="t">Contemporary Literature</span><span class="ln"></span></div>'
            f'<div class="answer">{_md_to_html(narrative)}</div>'
            f'<div class="sources">{"".join(rows)}</div></div>')


def _figures_html(result) -> str:
    out = []
    for f in (_g(result, "figures") or []):
        try:
            src = img_data_uri(_g(f, "image_path"))
        except Exception:
            continue  # unreadable -> skip the whole figure, never a broken <figure>
        loc = f'{html.escape(_g(f, "book") or "")}, p.{_g(f, "page")}'
        out.append(f'<figure><img src="{src}"><figcaption>'
                   f'<span class="fid">Fig [{_g(f, "source_n")}]</span> '
                   f'{html.escape(_g(f, "caption") or "")} <span class="cite">— {loc}</span>'
                   '</figcaption></figure>')
    return "".join(out)


def build_briefing_html(result, *, title: str, subtitle: str = "",
                        eyebrow: str = DEFAULT_EYEBROW, today: str | None = None) -> str:
    """Pure: render a Q&A result to an Executive-Navy HTML briefing string. Figures whose image
    file can't be read are skipped (never crash, never emit a broken image)."""
    today = today or dt.date.today().isoformat()
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><style>",
        EXEC_NAVY_CSS, ASK_CSS,
        "</style></head><body>",
        '<div class="masthead"><div class="mh-brand"><span class="sq"></span>NEURO·CASEBOARD</div>',
        '<div class="mh-eyebrow">Neurosurgery Signal · clinical briefing</div></div>',
        '<div class="content">',
        f'<span class="eyebrow">{html.escape(eyebrow)}</span>',
        f'<h1 class="title">{html.escape(title)}</h1>',
    ]
    if subtitle:
        parts.append(f'<div class="standfirst">{html.escape(subtitle)}</div>')
    parts.append('<div class="rule"></div>')
    parts.append(f'<div class="answer">{_md_to_html(_g(result, "answer") or "")}</div>')
    parts.append(_sources_html(result))
    parts.append(_literature_html(result))
    parts.append(_figures_html(result))
    parts.append("</div>")  # /content
    parts.append('<div class="footer">Generated from the neurosurgery textbook corpus · '
                 f'decision-support only · {html.escape(today)}</div>')
    parts.append("</body></html>")
    return "".join(parts)


def render_briefing_pdf(result, out_path, *, title: str, subtitle: str = "",
                        eyebrow: str = DEFAULT_EYEBROW) -> str:
    """Render the briefing to an A4 PDF via Playwright/Chromium. Requires the ``briefing`` extra
    and an installed Chromium binary."""
    from playwright.sync_api import sync_playwright
    doc = build_briefing_html(result, title=title, subtitle=subtitle, eyebrow=eyebrow)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(doc, wait_until="networkidle")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.pdf(path=str(out_path), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    return str(out_path)


def _plain(s: str) -> str:
    """Flatten inline **bold** to plain text -- the degraded offline path favours legibility."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s or "")


def _md_lines(md: str):
    """Yield (kind, text) for the minimal markdown the answer/narrative use."""
    for raw in (md or "").split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("### "):
            yield ("h3", s[4:]); continue
        if s.startswith("## "):
            yield ("h2", s[3:]); continue
        if s[:2] in ("* ", "- ") or s.startswith("*\t"):
            yield ("li", s[1:].strip()); continue
        yield ("p", s)


def render_briefing_clinical_pdf(result, out_path, *, title: str, subtitle: str = "") -> str:
    """Offline fpdf2 fallback (no Chromium): a clean clinical briefing for the Q&A result. Used
    when CASEBOARD_PDF_STYLE=clinical or when Chromium is unavailable."""
    import os
    from pathlib import Path
    from fpdf import FPDF
    from neuro_caseboard.fpdf_base import register_fonts, ascii_fallback

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    fam, uni = register_fonts(pdf)

    def t(s) -> str:
        s = _plain(str(s if s is not None else ""))
        return s if uni else ascii_fallback(s)

    pdf.set_font(fam, "B", 18)
    pdf.multi_cell(0, 9, t(title), new_x="LMARGIN", new_y="NEXT")
    if subtitle:
        pdf.set_font(fam, "I", 10)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 5, t(subtitle), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    for kind, text in _md_lines(_g(result, "answer") or ""):
        if kind == "h2":
            pdf.ln(1); pdf.set_font(fam, "B", 13)
            pdf.multi_cell(0, 7, t(text), new_x="LMARGIN", new_y="NEXT")
        elif kind == "h3":
            pdf.set_font(fam, "B", 11)
            pdf.multi_cell(0, 6, t(text), new_x="LMARGIN", new_y="NEXT")
        elif kind == "li":
            pdf.set_font(fam, "", 10); pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(0, 5, t("- " + text), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(fam, "", 10)
            pdf.multi_cell(0, 5, t(text), new_x="LMARGIN", new_y="NEXT")

    cites = _g(result, "citations") or []
    if cites:
        pdf.ln(2); pdf.set_font(fam, "B", 13)
        pdf.multi_cell(0, 7, t("Sources"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for c in cites:
            loc = _g(c, "book") or ""
            if _g(c, "chapter"):
                loc += f", {_g(c, 'chapter')}"
            loc += f", p.{_g(c, 'page')}"
            pdf.multi_cell(0, 4.6, t(f"[{_g(c, 'n')}] {loc}"), new_x="LMARGIN", new_y="NEXT")

    lit = _g(result, "literature")
    if lit and _g(lit, "narrative") and (_g(lit, "citations") or []):
        pdf.ln(2); pdf.set_font(fam, "B", 13)
        pdf.multi_cell(0, 7, t("Contemporary Literature"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 10)
        for kind, text in _md_lines(_g(lit, "narrative")):
            pdf.multi_cell(0, 5, t(("- " + text) if kind == "li" else text),
                           new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for c in (_g(lit, "citations") or []):
            doi = _g(c, "doi") or ""
            href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
            meta = ", ".join(p for p in (_g(c, "journal") or "", str(_g(c, "year") or "")) if p)
            pdf.multi_cell(0, 4.6, t(f"[L{_g(c, 'n')}] {_g(c, 'title') or ''} -- {meta} {href}"),
                           new_x="LMARGIN", new_y="NEXT")

    for f in (_g(result, "figures") or []):
        path = _g(f, "image_path")
        if path and os.path.exists(path):
            if pdf.get_y() + 70 > pdf.h - pdf.b_margin:
                pdf.add_page()
            try:
                pdf.image(path, w=min(pdf.epw, 110))
            except Exception:
                pass
        pdf.set_font(fam, "I", 8); pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 4, t(f"Fig [{_g(f, 'source_n')}] -- {_g(f, 'caption') or ''} "
                               f"({_g(f, 'book') or ''}, p.{_g(f, 'page')})"),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    out_path = Path(out_path)
    pdf.output(str(out_path))
    return str(out_path)
