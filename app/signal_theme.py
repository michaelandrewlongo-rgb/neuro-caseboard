"""Neuro·Caseboard — "Executive Navy" design system for the Streamlit console.

An editorial, clinical-grade reskin: a bright report content plane on a deep-navy navigation
rail, with a disciplined three-font system by role —

* **Archivo** (sans) ........ UI chrome: headings, nav, labels, metric numbers, buttons
* **Source Serif 4** (serif)  the reading column: answers, claims, the standfirst subtitle
* **IBM Plex Mono** ......... micro-labels: eyebrows, section keys, citations, tags

Grounded in how the best clinical answer engines and editorial/consulting surfaces read
(OpenEvidence/Perplexity citation patterns, FT/McKinsey serif gravitas, Stripe/Linear UI
restraint, UpToDate evidence grading). It deliberately drops the old neon glow, engineering
grid, and pulsing accent for calm authority. Still the on-screen sibling of the briefing PDF
(`neuro_caseboard/briefing_pdf.py`) — same navy/teal DNA, grown up.

Streamlit can't run React, so the look is delivered via `.streamlit/config.toml` (light base
tokens) + one injected stylesheet (`SIGNAL_CSS`) targeting stable `data-testid` nodes, plus pure
HTML helpers for the brand surfaces. Every helper escapes its inputs.
"""
from __future__ import annotations

import html
import re

import streamlit as st

SIGNAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=IBM+Plex+Mono:wght@500;600&display=swap');

:root{
  --page:#f6f7f9; --surface:#ffffff; --ink:#16202c; --muted:#586676; --faint:#8a96a2;
  --line:#e7e9ee; --line-soft:#eef0f3;
  --accent:#0e7490; --accent-2:#0891a5; --accent-soft:rgba(14,116,144,.38);
  --supported:#0f766e; --verify:#a9781b; --quar:#b4493b;
  --supported-bg:rgba(15,118,110,.09); --verify-bg:rgba(169,120,27,.10); --quar-bg:rgba(180,73,59,.09);
  --rail-bg:linear-gradient(180deg,#0c1626 0%,#0a1320 100%);
  --rail-ink:#eef3f8; --rail-muted:#8a98ab; --rail-line:rgba(148,163,184,.14); --rail-accent:#2bc4d4;
  --ui:'Archivo',system-ui,sans-serif;
  --read:'Source Serif 4',Georgia,'Times New Roman',serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
  --surface-2:#fbfcfd; --ease:cubic-bezier(.32,.72,0,1);
  --shadow-sm:0 0 0 1px rgba(16,32,48,.04),0 1px 2px rgba(16,32,48,.05);
  --shadow:0 0 0 1px rgba(16,32,48,.04),0 1px 2px rgba(16,32,48,.05),0 12px 26px rgba(16,32,48,.06);
}

/* ---- Canvas ---------------------------------------------------------------------------------- */
.stApp{ background:var(--page); }
[data-testid="stHeader"]{ background:transparent; }
#MainMenu, footer{ visibility:hidden; }
.stApp .block-container, [data-testid="stMainBlockContainer"]{
  max-width:1010px; padding-top:2.2rem; padding-bottom:5rem;
}
html, body, .stApp{ font-family:var(--ui); color:var(--ink); -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility; }
::selection{ background:rgba(14,116,144,.16); color:var(--ink); }

/* ---- Reading column = serif; UI chrome = sans ----------------------------------------------- */
.stMarkdown p, .stMarkdown li{
  font-family:var(--read); font-size:1.05rem; line-height:1.66; color:#1e2a36; max-width:74ch;
  font-optical-sizing:auto;
}
.stMarkdown strong{ color:#0c2233; font-weight:600; }
.stMarkdown a{ color:var(--accent); text-decoration:none; border-bottom:1px solid rgba(14,116,144,.28); }
.stMarkdown a:hover{ color:var(--accent-2); }
.stMarkdown h2{
  font-family:var(--ui); font-weight:700; font-size:1.3rem; color:var(--ink); letter-spacing:-.01em;
  margin:1.9rem 0 .6rem; padding-top:.9rem; border-top:1px solid var(--line);
}
.stMarkdown h2::before{
  content:""; display:inline-block; width:7px; height:7px; border-radius:2px; background:var(--accent);
  margin-right:11px; vertical-align:middle;
}
.stMarkdown h3{ font-family:var(--ui); color:var(--accent); font-weight:700; font-size:1.04rem; }
/* Inline citation chips — anchor-links that scroll to + flash their source row */
.cc, a.cc{ display:inline-flex; align-items:center; justify-content:center; font-family:var(--mono);
  font-size:.62rem; font-weight:600; color:var(--accent); background:rgba(14,116,144,.09);
  border:1px solid rgba(14,116,144,.22); border-radius:5px; padding:0 5px; margin:0 2px;
  transform:translateY(-1px); font-variant-numeric:tabular-nums; }
a.cc{ text-decoration:none; cursor:pointer; transition:background .14s var(--ease), border-color .14s var(--ease); }
@media (hover:hover){ a.cc:hover{ background:rgba(14,116,144,.16); border-color:var(--accent); } }

/* ---- Sidebar: deep-navy nav rail ------------------------------------------------------------ */
section[data-testid="stSidebar"]{ background:var(--rail-bg); border-right:1px solid var(--rail-line); }
section[data-testid="stSidebar"] .block-container{ padding-top:1.5rem; }
section[data-testid="stSidebar"] *{ color:var(--rail-ink); }
section[data-testid="stSidebar"] div[role="radiogroup"]{ gap:.25rem; margin-top:.2rem; }
section[data-testid="stSidebar"] div[role="radiogroup"] label{
  width:100%; padding:.55rem .75rem; border-radius:9px; border:1px solid transparent;
  font-family:var(--mono); font-size:.82rem; letter-spacing:.02em; color:var(--rail-muted);
  transition:all .15s ease;
}
@media (hover:hover){
  section[data-testid="stSidebar"] div[role="radiogroup"] label:hover{ background:rgba(255,255,255,.05); color:#fff; }
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:focus-within{ box-shadow:0 0 0 3px rgba(43,196,212,.3); }
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){
  background:rgba(43,196,212,.14); color:#fff; box-shadow:inset 2px 0 0 var(--rail-accent);
}
section[data-testid="stSidebar"] input[type="radio"]{ accent-color:var(--rail-accent); }
section[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"]{ background:var(--rail-accent); }

/* ---- Buttons: primary teal / secondary ghost ------------------------------------------------ */
.stButton>button, .stDownloadButton>button,
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"]{
  font-family:var(--ui); font-weight:600; letter-spacing:.01em; font-size:.86rem;
  border-radius:9px; padding:.55rem 1.2rem; box-shadow:var(--shadow-sm);
  transition:background .16s var(--ease), border-color .16s var(--ease),
             box-shadow .16s var(--ease), transform .12s var(--ease);
}
.stButton>button, [data-testid="stBaseButton-primary"], .stDownloadButton>button{
  color:#ffffff !important; background:var(--accent); border:1px solid var(--accent);
}
[data-testid="stBaseButton-secondary"]{
  color:var(--accent) !important; background:#ffffff; border:1px solid var(--line);
}
@media (hover:hover){
  .stButton>button:hover, [data-testid="stBaseButton-primary"]:hover, .stDownloadButton>button:hover{
    background:#0b6379; border-color:#0b6379; transform:translateY(-1px);
    box-shadow:0 8px 20px rgba(14,116,144,.22);
  }
  [data-testid="stBaseButton-secondary"]:hover{ border-color:var(--accent-soft); background:#f9fbfc; }
}
.stButton>button:active, .stDownloadButton>button:active,
[data-testid="stBaseButton-primary"]:active, [data-testid="stBaseButton-secondary"]:active{ transform:scale(.97); }
.stButton>button:focus-visible, .stDownloadButton>button:focus-visible,
[data-testid="stBaseButton-primary"]:focus-visible, [data-testid="stBaseButton-secondary"]:focus-visible,
[data-testid="stExpander"] summary:focus-visible{
  outline:none; box-shadow:0 0 0 3px rgba(14,116,144,.30);
}

/* ---- Inputs / select: command-bar feel ------------------------------------------------------ */
.stTextInput div[data-baseweb="input"], .stSelectbox div[data-baseweb="select"]>div{
  background:var(--surface) !important; border:1px solid var(--line) !important; border-radius:10px !important;
  box-shadow:var(--shadow-sm);
}
.stTextInput div[data-baseweb="input"]:focus-within{
  border-color:var(--accent) !important; box-shadow:0 0 0 3px rgba(14,116,144,.12) !important;
}
.stTextInput input{ background:transparent !important; color:var(--ink) !important; font-family:var(--ui); font-size:1rem; }
.stTextInput input::placeholder{ color:var(--faint) !important; }
.stTextInput label, .stSelectbox label, .stSlider label, .stCheckbox label span{ color:var(--muted) !important; }
.stTextInput label, .stSelectbox label{
  font-family:var(--mono); font-size:.7rem; letter-spacing:.08em; text-transform:uppercase;
}
section[data-testid="stSidebar"] .stSlider label{ font-family:var(--mono); font-size:.66rem;
  letter-spacing:.08em; text-transform:uppercase; color:var(--rail-muted) !important; }

/* ---- Surfaces: alerts, expanders, images ---------------------------------------------------- */
[data-testid="stAlert"]{ border-radius:11px; border:1px solid var(--line); font-family:var(--ui); box-shadow:var(--shadow-sm); }
[data-testid="stExpander"]{
  border:1px solid var(--line); border-left:3px solid var(--accent-soft); border-radius:12px;
  overflow:hidden; background:var(--surface-2); margin-bottom:.6rem; box-shadow:var(--shadow-sm);
}
[data-testid="stExpander"] summary{ font-family:var(--ui); font-weight:600; font-size:.92rem; color:var(--ink); }
@media (hover:hover){ [data-testid="stExpander"] summary:hover{ color:var(--accent); } }
[data-testid="stImage"] img, .stImage img{ border-radius:10px; border:1px solid var(--line); box-shadow:var(--shadow); }
[data-testid="stImageCaption"], .stImage figcaption{ color:var(--muted); font-size:.78rem; font-family:var(--ui); }
[data-testid="stSpinner"] *{ color:var(--accent) !important; }

::-webkit-scrollbar{ width:11px; height:11px; }
::-webkit-scrollbar-thumb{ background:#cdd5dd; border-radius:8px; border:3px solid var(--page); }
::-webkit-scrollbar-thumb:hover{ background:#b6c0c9; }

/* ---- Brand fragments ------------------------------------------------------------------------ */
.sig-eyebrow{
  display:inline-flex; align-items:center; border:1px solid rgba(14,116,144,.26);
  background:rgba(14,116,144,.06); border-radius:6px; padding:.3rem .7rem;
  font-family:var(--mono); font-size:.62rem; font-weight:600; letter-spacing:.18em;
  text-transform:uppercase; color:var(--accent);
}
.sig-eyebrow .dot{ width:6px; height:6px; border-radius:2px; background:var(--accent); margin-right:8px; }
.sig-title{
  font-family:var(--ui); font-weight:700; font-size:2rem; line-height:1.12; letter-spacing:-.02em;
  color:var(--ink); margin:1.1rem 0 .55rem; max-width:24ch;
}
.sig-subtitle{ font-family:var(--read); font-size:1.08rem; line-height:1.5; color:var(--muted); max-width:62ch;
  font-optical-sizing:auto; }
.sig-rule{ height:1px; background:var(--line); margin:1.3rem 0; }
.sig-disclaimer{ font-family:var(--mono); font-size:.68rem; letter-spacing:.04em; color:var(--faint); }
.sig-section{
  display:flex; align-items:center; gap:.85rem; margin:2.1rem 0 1rem;
}
.sig-section .k{ font-family:var(--mono); font-size:.68rem; font-weight:600; letter-spacing:.12em; color:var(--accent); }
.sig-section .t{ font-family:var(--ui); font-weight:700; font-size:1.22rem; letter-spacing:-.01em; color:var(--ink); }
.sig-section .ln{ flex:1; height:1px; background:var(--line); }
.sig-panel{
  background:var(--surface); border:1px solid var(--line); border-radius:13px; padding:.35rem 1.2rem;
  box-shadow:var(--shadow);
}
.sig-row{ font-family:var(--ui); font-size:.88rem; color:var(--muted); border-top:1px solid var(--line);
  padding:.7rem 0; scroll-margin-top:90px; }
.sig-row:first-child{ border-top:none; }
.sig-row:target{ animation:cc-flash 1.2s ease-out; }
@keyframes cc-flash{ 0%{ background:rgba(14,116,144,.14); } 100%{ background:transparent; } }
.sig-row .n{ font-family:var(--mono); color:var(--accent); font-weight:600; margin-right:7px; font-variant-numeric:tabular-nums; }
.sig-row .ln{ font-family:var(--mono); color:var(--accent-2); font-weight:600; margin-right:7px; font-variant-numeric:tabular-nums; }
.sig-row a{ color:var(--accent); text-decoration:none; }
.sig-metrics{ display:flex; flex-wrap:wrap; gap:.8rem; margin:.3rem 0 .7rem; }
.sig-metric{
  flex:1; min-width:140px; background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:.95rem 1.1rem; box-shadow:var(--shadow-sm);
}
.sig-metric .v{ font-family:var(--ui); font-weight:700; font-size:1.7rem; line-height:1; color:var(--ink);
  font-variant-numeric:tabular-nums; }
.sig-metric .k{ font-family:var(--mono); font-size:.6rem; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:.55rem; }
.sig-metric.supported .v{ color:var(--supported); }
.sig-metric.verify .v{ color:var(--verify); }
.sig-metric.quarantined .v{ color:var(--quar); }
.sig-legend{ display:flex; flex-wrap:wrap; gap:1.3rem; margin:.1rem 0 .4rem; }
.sig-legend .item{ display:flex; align-items:center; gap:.5rem; font-family:var(--ui); font-size:.8rem; color:var(--muted); }
.sig-legend .sw{ width:9px; height:9px; border-radius:50%; }
.sig-evbar{ display:flex; height:8px; border-radius:999px; overflow:hidden; background:var(--line-soft);
  box-shadow:inset 0 0 0 1px rgba(16,32,48,.05); margin:.1rem 0 1rem; }
.sig-evbar > span{ display:block; height:100%; }
.sig-evbar > span + span{ box-shadow:inset 1px 0 0 rgba(255,255,255,.65); }
.sig-hint{ display:flex; align-items:center; flex-wrap:wrap; gap:.5rem; margin:.9rem 0 0; }
.sig-hint .k{ font-family:var(--mono); font-size:.64rem; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); margin-right:.2rem; }
.sig-chip{ font-family:var(--read); font-size:.88rem; color:#33424f; background:var(--surface);
  border:1px solid var(--line); border-radius:999px; padding:.35rem .8rem; box-shadow:var(--shadow-sm); }
.sig-xref{ display:inline-block; font-family:var(--mono); font-size:.66rem; letter-spacing:.03em;
  color:var(--accent); background:rgba(14,116,144,.08); border:1px solid rgba(14,116,144,.22);
  border-radius:999px; padding:.12rem .55rem; margin-top:.35rem; }
.sig-variant{ display:inline-block; font-family:var(--read); font-size:.92rem; color:var(--ink);
  background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--accent-soft);
  border-radius:9px; padding:.45rem .8rem; margin:.25rem .45rem .25rem 0; box-shadow:var(--shadow-sm); }
.sig-note{ font-family:var(--read); border-left:2px solid var(--accent-soft); padding:.15rem 0 .15rem .85rem;
  margin:.7rem 0 .2rem; color:var(--muted); font-size:.92rem; }
.sig-note b{ color:var(--ink); }
.sig-wordmark{ font-family:var(--ui); font-weight:800; font-size:1.18rem; letter-spacing:-.01em;
  color:var(--rail-ink); display:flex; align-items:center; gap:.6rem; }
.sig-wordmark .wm{ line-height:1.0; }
.sig-wordmark .sq{ flex:0 0 auto; width:14px; height:14px; border-radius:3px; background:var(--rail-accent); }
.sig-tag{ font-family:var(--mono); font-size:.58rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--rail-muted); margin:.45rem 0 1.1rem; }
.sig-rail-label{ font-family:var(--mono); font-size:.58rem; letter-spacing:.16em; text-transform:uppercase;
  color:var(--rail-muted); margin:.5rem 0 .35rem; }
"""

_MARKER_TONES = {"supported": "var(--supported)", "verify": "var(--verify)", "quarantined": "var(--quar)"}


def _md(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


def apply_theme() -> None:
    """Inject the Executive Navy stylesheet. Call once, right after ``st.set_page_config``."""
    _md(f"<style>{SIGNAL_CSS}</style>")


def citation_chips(md: str) -> str:
    """Turn bare ``[n]`` / ``[L1]`` citation tokens in the answer markdown into inline anchor chips
    that scroll to (and flash) the matching Sources/Literature row, while leaving markdown links
    ``[text](url)`` untouched.

    The result is rendered with ``unsafe_allow_html=True``, so the surrounding text MUST be made
    inert first. A tag can only start with ``<``, so escaping ``&`` and ``<`` neutralises both
    HTML injection (a malicious ``<img onerror=...>`` topic) and silent content loss (clinical
    text like ``lesion <1 cm`` was being parsed as a tag and dropped). ``>`` is left intact on
    purpose so Markdown blockquotes (``> ...`` cross-refs in the board body) and ``>2 cm`` text
    still render; ``[`` and digits are untouched, so the citation regex still matches."""
    safe = (md or "").replace("&", "&amp;").replace("<", "&lt;")

    def _sub(m):
        tok = m.group(1)
        anchor = f"lit-{tok}" if tok.startswith("L") else f"src-{tok}"
        return f'<a class="cc" href="#{anchor}">{tok}</a>'

    return re.sub(r"\[(L?\d{1,3})\](?!\()", _sub, safe)


def hero(title: str, subtitle: str, *, eyebrow: str, disclaimer: str | None = None) -> None:
    """Kicker chip · sans headline · serif standfirst · hairline rule (the editorial page header)."""
    parts = [
        f'<span class="sig-eyebrow"><span class="dot"></span>{html.escape(eyebrow)}</span>',
        f'<div class="sig-title">{html.escape(title)}</div>',
        f'<div class="sig-subtitle">{html.escape(subtitle)}</div>',
        '<div class="sig-rule"></div>',
    ]
    if disclaimer:
        parts.append(f'<div class="sig-disclaimer">{html.escape(disclaimer)}</div>')
    _md("".join(parts))


def section(label: str, key: str = "") -> None:
    """A section header: optional mono key, sans title, hairline rule extending to the margin."""
    k = f'<span class="k">{html.escape(key)}</span>' if key else ""
    _md(f'<div class="sig-section">{k}<span class="t">{html.escape(label)}</span><span class="ln"></span></div>')


def note(text_html: str) -> None:
    """A quiet serif aside (accepts a small amount of inline HTML, e.g. <b>)."""
    _md(f'<div class="sig-note">{text_html}</div>')


def xref(text: str) -> None:
    _md(f'<span class="sig-xref">{html.escape(text)}</span>')


def evidence_bar(supported: int, verify: int, quarantined: int) -> None:
    """A compact stacked proportion bar (Consensus-meter style) of the board's evidence mix — the
    glance above the per-axis stat cards."""
    total = max(supported + verify + quarantined, 1)

    def seg(n, var):
        return f'<span style="width:{n / total * 100:.1f}%;background:{var}"></span>' if n else ""

    bar = (seg(supported, "var(--supported)") + seg(verify, "var(--verify)")
           + seg(quarantined, "var(--quar)"))
    _md(f'<div class="sig-evbar">{bar}</div>')


def metrics(items: list[tuple[object, str, str]]) -> None:
    """Stat cards. ``items`` = ``(value, label, tone)`` with tone in ``''|supported|verify|quarantined``."""
    cells = "".join(
        f'<div class="sig-metric {tone}"><div class="v">{html.escape(str(value))}</div>'
        f'<div class="k">{html.escape(label)}</div></div>'
        for value, label, tone in items
    )
    _md(f'<div class="sig-metrics">{cells}</div>')


def legend() -> None:
    """The evidence-axis legend (UpToDate-style) so the marker colours are self-explanatory."""
    items = [("Corpus-supported", "supported"), ("To verify", "verify"), ("Quarantined", "quarantined")]
    body = "".join(
        f'<div class="item"><span class="sw" style="background:{_MARKER_TONES[t]}"></span>{html.escape(lbl)}</div>'
        for lbl, t in items
    )
    _md(f'<div class="sig-legend">{body}</div>')


def example_hints(items: list[str], *, label: str = "Try") -> None:
    """Non-interactive example-prompt chips so an empty lane never reads as a blank void."""
    chips = "".join(f'<span class="sig-chip">{html.escape(s)}</span>' for s in items)
    _md(f'<div class="sig-hint"><span class="k">{html.escape(label)}</span>{chips}</div>')


def variants(labels: list[str]) -> None:
    chips = "".join(f'<span class="sig-variant">{html.escape(v)}</span>' for v in labels)
    _md(f"<div>{chips}</div>")


def sidebar_brand() -> None:
    st.sidebar.markdown(
        '<div class="sig-wordmark"><span class="sq"></span>'
        '<span class="wm">NEURO<br>CASEBOARD</span></div>'
        '<div class="sig-tag">Neurosurgery Signal · case-prep</div>',
        unsafe_allow_html=True,
    )


def sidebar_label(text: str) -> None:
    st.sidebar.markdown(f'<div class="sig-rail-label">{html.escape(text)}</div>', unsafe_allow_html=True)


def sources_panel(citations) -> None:
    rows = []
    for c in citations:
        chapter = getattr(c, "chapter", None)
        loc = getattr(c, "book", "") + (f", {chapter}" if chapter else "") + f", p.{getattr(c, 'page', '')}"
        n = getattr(c, "n", "?")
        rows.append(f'<div class="sig-row" id="src-{html.escape(str(n))}">'
                    f'<span class="n">[{n}]</span> {html.escape(loc)}</div>')
    _md(f'<div class="sig-panel">{"".join(rows)}</div>')


def literature_panel(citations) -> None:
    rows = []
    for c in citations:
        doi = getattr(c, "doi", None)
        href = f"https://doi.org/{doi}" if doi else (getattr(c, "url", "") or "")
        meta = " · ".join(p for p in [html.escape(getattr(c, "journal", "") or ""),
                                      str(getattr(c, "year", "") or "")] if p)
        link = f' · <a href="{html.escape(href)}" target="_blank" rel="noopener">link</a>' if href else ""
        n = getattr(c, "n", "?")
        rows.append(
            f'<div class="sig-row" id="lit-L{html.escape(str(n))}"><span class="ln">[L{n}]</span> '
            f'{html.escape(getattr(c, "title", "") or "")} '
            f'<span style="color:#8a96a2">— {meta}</span>{link}</div>')
    _md(f'<div class="sig-panel">{"".join(rows)}</div>')
