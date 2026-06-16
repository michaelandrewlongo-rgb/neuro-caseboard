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

import base64
import datetime as dt
import html
import os
import re

from neuro_caseboard.model import Dossier

# Mirrors app/signal_theme.py tokens, adapted to print (pt sizes, A4 full-bleed, page-break rules).
EXEC_NAVY_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=IBM+Plex+Mono:wght@500;600&display=swap');
:root{
  --ink:#16202c; --muted:#586676; --faint:#8a96a2; --line:#e7e9ee; --line-soft:#eef0f3;
  --accent:#0e7490; --accent-soft:rgba(14,116,144,.4);
  --supported:#0f766e; --verify:#a9781b; --quar:#b4493b;
  --supported-bg:rgba(15,118,110,.10); --verify-bg:rgba(169,120,27,.12);
  --ui:'Archivo',system-ui,sans-serif; --read:'Source Serif 4',Georgia,serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
}
@page{ size:A4; margin:0; }
*{ box-sizing:border-box; }
html,body{ margin:0; background:#ffffff; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body{ font-family:var(--ui); color:var(--ink); font-size:10.5pt; line-height:1.5;
  font-variant-numeric:tabular-nums; }

.masthead{ background:linear-gradient(105deg,#0c1626 0%,#0a1320 100%); color:#eef3f8; padding:13mm 18mm 9mm; }
.mh-brand{ display:flex; align-items:center; gap:9px; font-family:var(--ui); font-weight:800;
  font-size:13.5pt; letter-spacing:-.01em; }
.mh-brand .sq{ width:13px; height:13px; border-radius:3px; background:#2bc4d4; }
.mh-eyebrow{ font-family:var(--mono); font-size:7pt; letter-spacing:.2em; text-transform:uppercase;
  color:#9fb0c4; margin-top:3.5mm; }

.content{ padding:8mm 18mm 0; }
.eyebrow{ display:inline-block; font-family:var(--mono); font-size:6.6pt; font-weight:600;
  letter-spacing:.2em; text-transform:uppercase; color:var(--accent); border:1px solid rgba(14,116,144,.28);
  background:rgba(14,116,144,.06); border-radius:4px; padding:1.1mm 2.4mm; }
h1.title{ font-family:var(--ui); font-weight:700; font-size:21pt; letter-spacing:-.02em; line-height:1.12;
  margin:4.5mm 0 2mm; color:var(--ink); }
.standfirst{ font-family:var(--read); font-size:12pt; line-height:1.45; color:var(--muted);
  margin:0 0 4mm; max-width:165mm; }
.rule{ height:1px; background:var(--line); margin:5mm 0; }

.evbar{ display:flex; height:7px; border-radius:999px; overflow:hidden; background:var(--line-soft);
  box-shadow:inset 0 0 0 1px rgba(16,32,48,.06); margin:0 0 4mm; max-width:165mm; }
.evbar > span{ display:block; height:100%; }
.evbar > span + span{ box-shadow:inset 1px 0 0 rgba(255,255,255,.7); }
.metrics{ display:flex; gap:4mm; margin:0 0 3mm; }
.metric{ flex:1; border:1px solid var(--line); border-radius:10px; padding:3mm 4mm;
  box-shadow:0 1px 2px rgba(16,32,48,.04); }
.metric .v{ font-family:var(--ui); font-weight:700; font-size:16pt; line-height:1; color:var(--ink); }
.metric .k{ font-family:var(--mono); font-size:6.2pt; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:1.8mm; }
.metric.supported .v{ color:var(--supported); } .metric.verify .v{ color:var(--verify); }
.metric.quar .v{ color:var(--quar); }
.legend{ display:flex; gap:6mm; margin:0 0 1mm; font-family:var(--ui); font-size:8.4pt; color:var(--muted); }
.legend .item{ display:flex; align-items:center; gap:2mm; }
.legend .sw{ width:8px; height:8px; border-radius:50%; }

.section{ margin-top:7mm; }
.sec-h{ display:flex; align-items:center; gap:3mm; padding-top:3mm; border-top:1px solid var(--line);
  margin-bottom:3mm; break-after:avoid; }
.sec-h .k{ font-family:var(--mono); font-size:7pt; font-weight:600; letter-spacing:.12em; color:var(--accent); }
.sec-h .t{ font-family:var(--ui); font-weight:700; font-size:13pt; color:var(--ink); letter-spacing:-.01em; }
.sec-h .ln{ flex:1; height:1px; background:var(--line); }
.sec-intro{ font-family:var(--read); font-style:italic; color:var(--muted); margin:0 0 3mm; max-width:165mm; }

.claim{ border:1px solid var(--line); border-left:3px solid var(--line); border-radius:9px;
  padding:3mm 4mm; margin-bottom:2.6mm; break-inside:avoid; box-shadow:0 1px 2px rgba(16,32,48,.04); }
.claim.supported{ border-left-color:var(--supported); }
.claim.verify{ border-left-color:var(--verify); }
.marker{ display:inline-block; font-family:var(--mono); font-size:6.4pt; font-weight:600; letter-spacing:.1em;
  text-transform:uppercase; padding:1mm 2.6mm; border-radius:999px; margin-bottom:2mm; }
.marker.supported{ color:var(--supported); background:var(--supported-bg); }
.marker.verify{ color:var(--verify); background:var(--verify-bg); }
.claim .ctext{ font-family:var(--read); font-size:11pt; line-height:1.46; color:#1e2a36; }
.claim .ctext b{ color:#0c2233; font-weight:600; }
.figref{ font-family:var(--mono); font-size:6.8pt; color:var(--accent); white-space:nowrap; }
.why{ font-family:var(--read); font-size:9.8pt; line-height:1.42; color:var(--muted);
  border-left:2px solid var(--accent-soft); padding-left:3mm; margin-top:2mm; }
.why b{ font-family:var(--mono); font-size:6.4pt; letter-spacing:.1em; text-transform:uppercase;
  color:var(--accent); font-weight:600; margin-right:2mm; }
.subs{ margin:2mm 0 0; padding:0; }
.subs li{ list-style:none; font-family:var(--read); font-size:9.8pt; color:#33424f; margin:0 0 1mm; padding-left:6mm;
  text-indent:-6mm; }
.subs li::before{ content:"\\2610"; color:var(--accent); margin-right:2.4mm; }
.xnote{ font-family:var(--read); font-style:italic; color:var(--muted); font-size:9.4pt;
  border-left:2px solid var(--line); padding-left:3mm; margin:2mm 0; }

figure{ break-inside:avoid; margin:0 0 4mm; border:1px solid var(--line); border-radius:11px; overflow:hidden;
  box-shadow:0 1px 2px rgba(16,32,48,.04); }
figure img{ display:block; width:100%; max-height:115mm; object-fit:contain; background:#f3f5f7; }
figcaption{ padding:3mm 4mm; font-family:var(--read); font-size:9.6pt; line-height:1.4; color:var(--muted); }
figcaption .fid{ font-family:var(--mono); font-size:7pt; color:var(--accent); font-weight:600; margin-right:2mm; }
figcaption .rel{ display:block; margin-top:1.4mm; color:#33424f; }
figcaption .cite{ color:var(--faint); }

.appendix{ margin-top:7mm; }
.appendix .ap-h{ font-family:var(--ui); font-weight:700; font-size:10pt; color:var(--ink); margin:3mm 0 1.5mm; }
.appendix ul{ margin:0 0 2mm; padding-left:5mm; }
.appendix li{ font-family:var(--read); font-size:9.4pt; color:var(--muted); margin-bottom:.8mm; }
.footer{ margin-top:8mm; padding:4mm 18mm 10mm; border-top:1px solid var(--line);
  font-family:var(--mono); font-size:7pt; letter-spacing:.04em; color:var(--faint); }
"""

_STATUS_LABEL = {"supported": "Corpus-supported", "verify": "To verify"}


def _inline(text: str) -> str:
    """Escape, then promote ``**bold**`` to <b> (the only inline markup claims/why use)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text or ""))


def _img_data_uri(path: str) -> str:
    # Derive the extension from the basename only — a dot in a parent dir (e.g. /data/v1.2/figA)
    # or a missing extension must not corrupt the MIME type.
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, f"image/{ext}")
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


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
             f'<div class="ctext">{_inline(c.text)}{figref}</div>']
    if c.why:
        parts.append(f'<div class="why"><b>Why</b>{_inline(c.why)}</div>')
    if c.sub_items:
        parts.append('<ul class="subs">' + "".join(f"<li>{_inline(i)}</li>" for i in c.sub_items) + "</ul>")
    parts.append("</div>")
    return "".join(parts)


def _figure_html(fig) -> str:
    try:
        img = f'<img src="{_img_data_uri(fig.image_path)}">'
    except Exception:
        img = ""  # never emit a broken image; keep the caption
    cite = f' <span class="cite">— {html.escape(fig.citation)}</span>' if fig.citation else ""
    rel = f'<span class="rel">{_inline(fig.relevance)}</span>' if fig.relevance else ""
    return (f'<figure>{img}<figcaption><span class="fid">Fig {html.escape(fig.fig_id)}</span>'
            f'{_inline(fig.caption)}{cite}{rel}</figcaption></figure>')


def build_caseboard_html(dossier: Dossier, *, subtitle: str = "", today: str | None = None) -> str:
    """Pure: render a Dossier to an Executive-Navy HTML string (figures whose file can't be read
    are kept caption-only, never crash)."""
    today = today or dt.date.today().isoformat()
    s = dossier.summary
    keys = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

    out = [
        "<!doctype html><html><head><meta charset='utf-8'><style>", EXEC_NAVY_CSS, "</style></head><body>",
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
            out.append(f'<div class="sec-intro">{_inline(sec.intro)}</div>')
        for c in sec.claims:
            out.append(_claim_html(c))
        for fig in sec.figures:
            if fig.image_path in seen:
                continue
            seen.add(fig.image_path)
            out.append(_figure_html(fig))
        for ref in sec.cross_refs:
            out.append(f'<div class="xnote">{_inline(ref)}</div>')
        out.append("</div>")

    if not dossier.appendix.is_empty():
        out.append('<div class="appendix"><div class="sec-h"><span class="k">APX</span>'
                   '<span class="t">Appendix — evidence sources & off-target claims</span>'
                   '<span class="ln"></span></div>')
        for e in dossier.appendix.entries:
            out.append(f'<div class="ap-h">{html.escape(e.heading)}</div><ul>')
            for it in e.items:
                out.append(f"<li>{_inline(it)}</li>")
            for sr in e.sources:
                out.append(f"<li>{_inline(sr)}</li>")
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
