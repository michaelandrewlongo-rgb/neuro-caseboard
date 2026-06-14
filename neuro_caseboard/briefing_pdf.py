"""Signal-styled briefing PDF export for Q&A results.

Renders a query result (answer + numbered citations + figures) as a single HTML document styled
to match the Neurosurgery Signal v1 web app — dark navy canvas with teal/red "signal" accents,
Syne display headings, Inter body, monospace eyebrow chips, and bordered surface panels — then
converts HTML -> PDF with Playwright/Chromium.

Design tokens are mirrored from that app's ``web/src/app/globals.css`` so the briefing matches the
site brand exactly (teal ``#22d3ee`` / ``#67e8f9``, red signal ``#ef4444``, navy ``#070c14``).

``build_briefing_html`` is pure and dependency-light (unit-tested). ``render_briefing_pdf`` needs
Playwright + a Chromium binary (an optional dependency):

    pip install -e ".[briefing]" && playwright install chromium
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import re

DEFAULT_EYEBROW = "Neurosurgery Signal · Clinical Briefing"

# Mirrored from neurosurgery-signal-v1 web/src/app/globals.css (@theme tokens + surface/eyebrow
# rules), adapted for print (full-bleed dark page on every sheet, Google-hosted Syne/Inter/mono).
SIGNAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;600&display=swap');
*{box-sizing:border-box;}
html{margin:0;background:#080d16;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
body{margin:0;color:#f8fafc;font-family:Inter,system-ui,sans-serif;font-size:11pt;line-height:1.62;
  padding:20mm 18mm;
  background:
    radial-gradient(circle at 12% 2%, rgba(34,211,238,.16), transparent 40%),
    radial-gradient(circle at 86% 12%, rgba(239,68,68,.10), transparent 36%),
    linear-gradient(rgba(148,163,184,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148,163,184,.05) 1px, transparent 1px),
    linear-gradient(165deg,#05070d 0%,#0a111b 48%,#0b1220 100%);
  background-size:auto,auto,56px 56px,56px 56px,auto;}
p{margin:0 0 10px;max-width:680px;text-wrap:pretty;}
ul{margin:0 0 12px;padding-left:20px;max-width:680px;} li{margin:0 0 5px;}
strong{font-weight:600;color:#ffffff;}
.eyebrow{display:inline-flex;align-items:center;border:1px solid rgba(34,211,238,.34);
  background:rgba(15,23,42,.68);border-radius:9999px;padding:.3rem .85rem;
  font-family:"JetBrains Mono",ui-monospace,monospace;font-size:7.6pt;font-weight:600;
  letter-spacing:.18em;text-transform:uppercase;color:#67e8f9;}
.eyebrow .dot{width:6px;height:6px;border-radius:50%;background:#ef4444;
  box-shadow:0 0 8px rgba(239,68,68,.85);margin-right:8px;}
h1{font-family:Syne,system-ui,sans-serif;font-weight:700;font-size:29pt;line-height:1.0;
  letter-spacing:-.035em;text-wrap:balance;margin:16px 0 8px;
  background:linear-gradient(180deg,#f8fafc 0%,#cbd5e1 100%);-webkit-background-clip:text;
  background-clip:text;-webkit-text-fill-color:transparent;}
.subtitle{color:#94a3b8;font-size:12pt;margin:0;max-width:680px;}
.rule{height:2px;width:128px;background:linear-gradient(90deg,#67e8f9,#22d3ee,#0e7490);
  margin:16px 0 20px;border-radius:2px;box-shadow:0 0 14px rgba(34,211,238,.45);}
.disclaimer{color:#64748b;font-size:8pt;font-family:"JetBrains Mono",ui-monospace,monospace;
  letter-spacing:.04em;margin-bottom:26px;}
h2{font-family:Syne,system-ui,sans-serif;font-weight:700;font-size:17pt;color:#f8fafc;
  margin:28px 0 8px;padding-top:14px;border-top:1px solid rgba(71,85,105,.5);}
h2::before{content:"";display:inline-block;width:8px;height:8px;border-radius:2px;background:#ef4444;
  box-shadow:0 0 9px rgba(239,68,68,.65);margin-right:11px;vertical-align:middle;}
h3{font-family:Syne,system-ui,sans-serif;font-weight:700;font-size:13pt;color:#67e8f9;margin:18px 0 5px;}
.sources{margin-top:10px;max-width:680px;border:1px solid rgba(71,85,105,.5);border-radius:.75rem;
  background:linear-gradient(165deg,rgba(17,24,39,.86),rgba(10,15,26,.94));padding:14px 18px;
  box-shadow:0 18px 44px rgba(2,6,23,.4),inset 0 1px 0 rgba(148,163,184,.12);}
.src{font-size:9.3pt;color:#94a3b8;border-top:1px solid rgba(71,85,105,.4);padding:6px 0;}
.src:first-child{border-top:none;padding-top:0;}
.src .n{color:#22d3ee;font-weight:600;font-family:"JetBrains Mono",ui-monospace,monospace;}
.src .ln{color:#67e8f9;font-weight:600;font-family:"JetBrains Mono",ui-monospace,monospace;}
.src a{color:#22d3ee;text-decoration:none;}
.litmeta{color:#cbd5e1;}
figure{page-break-before:always;margin:0;}
.figlabel{margin-bottom:10px;}
figure img{display:block;margin:0 auto;max-width:100%;max-height:198mm;height:auto;border-radius:.6rem;
  border:1px solid rgba(34,211,238,.28);box-shadow:0 0 22px rgba(34,211,238,.06);}
figcaption{color:#94a3b8;font-size:9.3pt;margin-top:12px;max-width:680px;}
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
        rows.append(
            f'<div class="src"><span class="ln">[L{_g(c, "n")}]</span> '
            f'{html.escape(_g(c, "title") or "")} '
            f'<span class="litmeta">— {meta}</span>{link}</div>')
    return ("<h2>Contemporary Literature</h2>"
            + _md_to_html(narrative)
            + f'<div class="sources">{"".join(rows)}</div>')


def _img_data(path: str) -> str:
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def build_briefing_html(result, *, title: str, subtitle: str = "",
                        eyebrow: str = DEFAULT_EYEBROW, today: str | None = None) -> str:
    """Pure: render a query result to a Signal-styled HTML briefing string. Figures whose image
    file can't be read are skipped (never crash / never emit a broken image)."""
    today = today or dt.date.today().isoformat()
    answer = _md_to_html(_g(result, "answer") or "")
    sources = "\n".join(
        f'<div class="src"><span class="n">[{_g(c, "n")}]</span> {html.escape(_g(c, "book") or "")}'
        + (f", {html.escape(_g(c, 'chapter'))}" if _g(c, "chapter") else "")
        + f", p.{_g(c, 'page')}</div>"
        for c in (_g(result, "citations") or []))
    figs = []
    for f in (_g(result, "figures") or []):
        try:
            data = _img_data(_g(f, "image_path"))
        except Exception:
            continue
        figs.append(
            f'<figure><div class="eyebrow figlabel">Figure [{_g(f, "source_n")}] · '
            f'{html.escape(_g(f, "book") or "")}, p.{_g(f, "page")}</div>'
            f'<img src="{data}"><figcaption>{html.escape(_g(f, "caption") or "")}</figcaption></figure>')
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>" + SIGNAL_CSS + "</style></head><body>"
        + f'<div class="eyebrow"><span class="dot"></span>{html.escape(eyebrow)}</div>'
        + f"<h1>{html.escape(title)}</h1>"
        + (f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else "")
        + '<div class="rule"></div>'
        + f'<div class="disclaimer">Generated from the neurosurgery textbook corpus · '
          f'decision-support only · {today}</div>'
        + answer
        + "<h2>Sources</h2>"
        + f'<div class="sources">{sources}</div>'
        + _literature_html(result)
        + "\n".join(figs)
        + "</body></html>")


def render_briefing_pdf(result, out_path, *, title: str, subtitle: str = "",
                        eyebrow: str = DEFAULT_EYEBROW) -> str:
    """Render the briefing to a PDF at ``out_path`` (A4) via Playwright/Chromium. Requires the
    ``briefing`` optional dependency and an installed Chromium binary."""
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
