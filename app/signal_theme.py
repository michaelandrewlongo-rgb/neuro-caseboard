"""Neurosurgery Signal — screen design system for the Streamlit case-prep console.

This is the on-screen sibling of ``neuro_caseboard/briefing_pdf.py``: the same brand tokens
(teal ``#22d3ee`` / ``#67e8f9``, red signal ``#ef4444``, navy ``#080d16``, Syne display, Inter
body, JetBrains Mono eyebrows) adapted from print to a live dark canvas. Streamlit can't run
arbitrary React, so the look is delivered in two ways:

* ``.streamlit/config.toml`` sets the base dark tokens (robust across versions).
* ``SIGNAL_CSS`` (injected once via :func:`apply_theme`) restyles Streamlit's own DOM using
  stable ``data-testid`` selectors, then a handful of pure HTML helpers render the
  brand-defining surfaces (hero, section rules, evidence panels, metric chips).

Every helper escapes its inputs and emits self-contained HTML so the caller stays declarative.
"""
from __future__ import annotations

import html

import streamlit as st

# --- The design system -------------------------------------------------------------------------
# Tokens mirror briefing_pdf.SIGNAL_CSS. Selectors target Streamlit 1.5x test-ids / base-web
# nodes; anything missed still lands on the dark config base, so the app never falls back to
# stock white.
SIGNAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

:root{
  --bg:#080d16; --ink:#f8fafc; --muted:#94a3b8; --faint:#64748b;
  --teal:#22d3ee; --teal-2:#67e8f9; --teal-deep:#0e7490; --red:#ef4444;
  --border:rgba(71,85,105,.5); --border-teal:rgba(34,211,238,.34);
  --panel:linear-gradient(165deg,rgba(17,24,39,.86),rgba(10,15,26,.94));
  --display:'Syne',system-ui,sans-serif;
  --body:'Inter',system-ui,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,monospace;
}

/* ---- Canvas: navy gradient + faint engineering grid + signal glows -------------------------- */
.stApp{
  background:
    radial-gradient(circle at 12% 2%, rgba(34,211,238,.16), transparent 40%),
    radial-gradient(circle at 86% 10%, rgba(239,68,68,.10), transparent 36%),
    linear-gradient(rgba(148,163,184,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148,163,184,.05) 1px, transparent 1px),
    linear-gradient(165deg,#05070d 0%,#0a111b 48%,#0b1220 100%);
  background-size:auto,auto,56px 56px,56px 56px,auto;
  background-attachment:fixed;
}
[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer{visibility:hidden;}
.stApp .block-container, [data-testid="stMainBlockContainer"]{
  max-width:1080px; padding-top:2.2rem; padding-bottom:5rem;
}

/* ---- Typography ----------------------------------------------------------------------------- */
html, body, .stApp, .stMarkdown, [data-testid="stMarkdownContainer"]{
  font-family:var(--body); color:var(--ink);
}
.stApp h1, .stApp h2, .stApp h3, .stApp h4{ font-family:var(--display); letter-spacing:-.02em; }
.stMarkdown h2{
  font-family:var(--display); font-weight:700; font-size:1.35rem; color:var(--ink);
  margin:1.8rem 0 .6rem; padding-top:.9rem; border-top:1px solid var(--border);
}
.stMarkdown h2::before{
  content:""; display:inline-block; width:8px; height:8px; border-radius:2px; background:var(--red);
  box-shadow:0 0 9px rgba(239,68,68,.65); margin-right:11px; vertical-align:middle;
}
.stMarkdown h3{ font-family:var(--display); color:var(--teal-2); font-weight:700; font-size:1.05rem; }
.stMarkdown p, .stMarkdown li{ max-width:760px; }
.stMarkdown a{ color:var(--teal); text-decoration:none; border-bottom:1px solid rgba(34,211,238,.3); }
.stMarkdown a:hover{ color:var(--teal-2); border-color:var(--teal-2); }
.stMarkdown strong{ color:#fff; font-weight:600; }

/* ---- Sidebar: branded console rail ---------------------------------------------------------- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#070c15,#0a1120); border-right:1px solid var(--border);
}
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }
section[data-testid="stSidebar"] div[role="radiogroup"]{ gap:.25rem; }
section[data-testid="stSidebar"] div[role="radiogroup"] label{
  width:100%; padding:.5rem .7rem; border-radius:10px; border:1px solid transparent;
  font-family:var(--mono); font-size:.82rem; letter-spacing:.02em; color:var(--muted);
  transition:all .15s ease;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover{
  background:rgba(34,211,238,.06); color:var(--teal-2);
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){
  background:linear-gradient(90deg,rgba(34,211,238,.14),transparent);
  border-color:var(--border-teal); color:var(--ink); box-shadow:inset 2px 0 0 var(--teal);
}
section[data-testid="stSidebar"] input[type="radio"]{ accent-color:var(--teal); }

/* ---- Buttons: teal signal ------------------------------------------------------------------- */
.stButton>button, .stDownloadButton>button{
  font-family:var(--mono); font-weight:600; letter-spacing:.05em; text-transform:uppercase;
  font-size:.76rem; color:#04141a;
  background:linear-gradient(180deg,var(--teal-2),var(--teal));
  border:1px solid rgba(34,211,238,.6); border-radius:9px; padding:.5rem 1.1rem;
  box-shadow:0 8px 22px rgba(34,211,238,.12); transition:all .18s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover{
  transform:translateY(-1px); border-color:var(--teal-2); color:#04141a;
  box-shadow:0 0 18px rgba(34,211,238,.45), 0 10px 26px rgba(34,211,238,.2);
}
.stButton>button:focus, .stDownloadButton>button:focus{ color:#04141a; }

/* ---- Inputs / select ------------------------------------------------------------------------ */
.stTextInput div[data-baseweb="input"], .stSelectbox div[data-baseweb="select"]>div{
  background:rgba(8,13,22,.7)!important; border:1px solid var(--border)!important;
  border-radius:10px!important;
}
.stTextInput div[data-baseweb="input"]:focus-within{
  border-color:var(--teal)!important; box-shadow:0 0 0 3px rgba(34,211,238,.14)!important;
}
.stTextInput input{ background:transparent!important; color:var(--ink)!important; font-family:var(--body); }
.stTextInput label, .stCheckbox label span, .stSelectbox label, .stSlider label{
  color:var(--muted)!important;
}
.stTextInput label, .stSelectbox label, .stSlider label{
  font-family:var(--mono); font-size:.72rem; letter-spacing:.05em; text-transform:uppercase;
}

/* ---- Surfaces: alerts, expanders, images ---------------------------------------------------- */
[data-testid="stAlert"]{ border-radius:12px; border:1px solid var(--border); font-family:var(--body); }
[data-testid="stExpander"]{
  border:1px solid var(--border); border-radius:12px; overflow:hidden;
  background:var(--panel); margin-bottom:.55rem;
}
[data-testid="stExpander"] summary{ font-family:var(--mono); font-size:.84rem; color:var(--ink); }
[data-testid="stExpander"] summary:hover{ color:var(--teal-2); }
[data-testid="stImage"] img, .stImage img{
  border-radius:.6rem; border:1px solid rgba(34,211,238,.28); box-shadow:0 0 22px rgba(34,211,238,.06);
}
[data-testid="stImageCaption"], .stImage figcaption{
  color:var(--muted); font-size:.78rem; font-family:var(--body);
}
[data-testid="stSpinner"] *{ color:var(--teal-2)!important; }

/* ---- Scrollbar ------------------------------------------------------------------------------ */
::-webkit-scrollbar{ width:10px; height:10px; }
::-webkit-scrollbar-thumb{ background:rgba(34,211,238,.25); border-radius:8px; }
::-webkit-scrollbar-thumb:hover{ background:rgba(34,211,238,.4); }
::-webkit-scrollbar-track{ background:transparent; }

/* ---- Brand fragments (rendered by the helpers below) ---------------------------------------- */
.sig-hero{ animation:sig-rise .5s cubic-bezier(.2,.7,.2,1) both; margin-bottom:.6rem; }
@keyframes sig-rise{ from{opacity:0; transform:translateY(10px);} to{opacity:1; transform:none;} }
.sig-eyebrow{
  display:inline-flex; align-items:center; border:1px solid var(--border-teal);
  background:rgba(15,23,42,.68); border-radius:9999px; padding:.32rem .85rem;
  font-family:var(--mono); font-size:.66rem; font-weight:600; letter-spacing:.18em;
  text-transform:uppercase; color:var(--teal-2);
}
.sig-eyebrow .dot{
  width:6px; height:6px; border-radius:50%; background:var(--red); margin-right:8px;
  box-shadow:0 0 8px rgba(239,68,68,.85); animation:sig-pulse 2.4s ease-in-out infinite;
}
@keyframes sig-pulse{ 0%,100%{opacity:1;} 50%{opacity:.5;} }
.sig-title{
  font-family:var(--display); font-weight:800; font-size:2.55rem; line-height:1.02;
  letter-spacing:-.035em; margin:.7rem 0 .35rem;
  background:linear-gradient(180deg,#f8fafc 0%,#cbd5e1 100%);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
}
.sig-subtitle{ color:var(--muted); font-size:1.02rem; max-width:700px; margin:0; }
.sig-rule{
  height:2px; width:128px; border-radius:2px; margin:1rem 0 .9rem;
  background:linear-gradient(90deg,#67e8f9,#22d3ee,#0e7490); box-shadow:0 0 14px rgba(34,211,238,.45);
}
.sig-disclaimer{
  color:var(--faint); font-size:.72rem; font-family:var(--mono); letter-spacing:.04em;
}
.sig-section{
  display:flex; align-items:center; gap:.6rem; font-family:var(--display); font-weight:700;
  font-size:1.25rem; color:var(--ink); margin:1.9rem 0 .7rem; padding-top:.9rem;
  border-top:1px solid var(--border);
}
.sig-section::before{
  content:""; width:8px; height:8px; border-radius:2px; background:var(--red);
  box-shadow:0 0 9px rgba(239,68,68,.65);
}
.sig-panel{
  border:1px solid var(--border); border-radius:14px; background:var(--panel); padding:.3rem 1.1rem;
  box-shadow:0 18px 44px rgba(2,6,23,.4), inset 0 1px 0 rgba(148,163,184,.12);
}
.sig-row{ font-size:.86rem; color:var(--muted); border-top:1px solid rgba(71,85,105,.4); padding:.55rem 0; }
.sig-row:first-child{ border-top:none; }
.sig-row .n{ color:var(--teal); font-weight:600; font-family:var(--mono); }
.sig-row .ln{ color:var(--teal-2); font-weight:600; font-family:var(--mono); }
.sig-row a{ color:var(--teal); text-decoration:none; }
.sig-row a:hover{ color:var(--teal-2); }
.sig-metrics{ display:flex; flex-wrap:wrap; gap:.6rem; margin:.2rem 0 1.1rem; }
.sig-metric{
  border:1px solid var(--border); border-radius:12px; background:rgba(8,13,22,.5);
  padding:.6rem .95rem; min-width:118px;
}
.sig-metric .v{ font-family:var(--display); font-weight:800; font-size:1.5rem; line-height:1; }
.sig-metric .k{
  font-family:var(--mono); font-size:.62rem; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:.3rem;
}
.sig-metric.ink .v{ color:var(--ink); }
.sig-metric.teal .v{ color:var(--teal-2); }
.sig-metric.amber .v{ color:#fbbf24; }
.sig-metric.red .v{ color:#f87171; }
.sig-xref{
  display:inline-block; font-family:var(--mono); font-size:.66rem; letter-spacing:.04em;
  color:var(--teal-2); background:rgba(34,211,238,.08); border:1px solid var(--border-teal);
  border-radius:9999px; padding:.12rem .5rem; margin-top:.35rem;
}
.sig-variant{
  display:inline-block; font-family:var(--mono); font-size:.78rem; color:var(--ink);
  background:rgba(34,211,238,.06); border:1px solid var(--border-teal); border-radius:9px;
  padding:.35rem .7rem; margin:.25rem .4rem .25rem 0;
}
.sig-wordmark{
  font-family:var(--display); font-weight:800; font-size:1.18rem; letter-spacing:-.01em;
  color:var(--ink); display:flex; align-items:center; gap:.55rem;
}
.sig-wordmark .wm{ line-height:1.0; }
.sig-wordmark .sq{
  flex:0 0 auto; width:14px; height:14px; border-radius:3px; box-shadow:0 0 12px rgba(34,211,238,.5);
  background:linear-gradient(135deg,var(--teal-2),var(--teal-deep));
}
.sig-tag{
  font-family:var(--mono); font-size:.6rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--faint); margin:.4rem 0 1rem;
}
.sig-rail-label{
  font-family:var(--mono); font-size:.6rem; letter-spacing:.16em; text-transform:uppercase;
  color:var(--faint); margin:.4rem 0 .4rem;
}
.sig-note{
  border-left:2px solid var(--teal-deep); padding:.1rem 0 .1rem .8rem; margin:.6rem 0 1rem;
  color:var(--muted); font-size:.82rem;
}
"""


def _md(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


def apply_theme() -> None:
    """Inject the Signal design system. Call once, right after ``st.set_page_config``."""
    _md(f"<style>{SIGNAL_CSS}</style>")


def eyebrow_html(text: str) -> str:
    """The monospace pill chip with a pulsing red signal dot (returns raw HTML)."""
    return f'<span class="sig-eyebrow"><span class="dot"></span>{html.escape(text)}</span>'


def hero(title: str, subtitle: str, *, eyebrow: str, disclaimer: str | None = None) -> None:
    """The brand-defining page header: eyebrow chip, gradient Syne title, subtitle, signal rule."""
    parts = [
        '<div class="sig-hero">',
        eyebrow_html(eyebrow),
        f'<div class="sig-title">{html.escape(title)}</div>',
        f'<div class="sig-subtitle">{html.escape(subtitle)}</div>',
        '<div class="sig-rule"></div>',
    ]
    if disclaimer:
        parts.append(f'<div class="sig-disclaimer">{html.escape(disclaimer)}</div>')
    parts.append("</div>")
    _md("".join(parts))


def section(label: str) -> None:
    """A Syne section header with the red square marker + hairline rule (matches the briefing PDF)."""
    _md(f'<div class="sig-section">{html.escape(label)}</div>')


def note(text: str) -> None:
    """A quiet teal-ruled aside for secondary guidance."""
    _md(f'<div class="sig-note">{html.escape(text)}</div>')


def xref(text: str) -> None:
    """The small teal cross-reference chip used under cross-linked figures."""
    _md(f'<span class="sig-xref">{html.escape(text)}</span>')


def metrics(items: list[tuple[object, str, str]]) -> None:
    """Render a row of stat chips. ``items`` = ``(value, label, tone)`` with tone in
    ``ink|teal|amber|red``."""
    cells = "".join(
        f'<div class="sig-metric {tone}"><div class="v">{html.escape(str(value))}</div>'
        f'<div class="k">{html.escape(label)}</div></div>'
        for value, label, tone in items
    )
    _md(f'<div class="sig-metrics">{cells}</div>')


def variants(labels: list[str]) -> None:
    """Render disambiguation variants as selectable-looking chips."""
    chips = "".join(f'<span class="sig-variant">{html.escape(v)}</span>' for v in labels)
    _md(f"<div>{chips}</div>")


def sidebar_brand() -> None:
    """The console wordmark + tagline at the top of the rail."""
    st.sidebar.markdown(
        '<div class="sig-wordmark"><span class="sq"></span>'
        '<span class="wm">NEURO<br>CASEBOARD</span></div>'
        '<div class="sig-tag">Neurosurgery Signal · case-prep console</div>',
        unsafe_allow_html=True,
    )


def sidebar_label(text: str) -> None:
    """A small monospace eyebrow used to title a sidebar group."""
    st.sidebar.markdown(f'<div class="sig-rail-label">{html.escape(text)}</div>',
                        unsafe_allow_html=True)


def sources_panel(citations) -> None:
    """A bordered surface listing textbook citations: ``[n] Book, Chapter, p.N``."""
    rows = []
    for c in citations:
        chapter = getattr(c, "chapter", None)
        loc = getattr(c, "book", "") + (f", {chapter}" if chapter else "") + f", p.{getattr(c, 'page', '')}"
        rows.append(f'<div class="sig-row"><span class="n">[{getattr(c, "n", "?")}]</span> '
                    f'{html.escape(loc)}</div>')
    _md(f'<div class="sig-panel">{"".join(rows)}</div>')


def literature_panel(citations) -> None:
    """A bordered surface listing PubMed literature: ``[L#] Title — Journal · Year · link``."""
    rows = []
    for c in citations:
        doi = getattr(c, "doi", None)
        href = f"https://doi.org/{doi}" if doi else (getattr(c, "url", "") or "")
        meta = " · ".join(p for p in [html.escape(getattr(c, "journal", "") or ""),
                                      str(getattr(c, "year", "") or "")] if p)
        link = f' · <a href="{html.escape(href)}" target="_blank" rel="noopener">link</a>' if href else ""
        rows.append(
            f'<div class="sig-row"><span class="ln">[L{getattr(c, "n", "?")}]</span> '
            f'{html.escape(getattr(c, "title", "") or "")} '
            f'<span style="color:#cbd5e1">— {meta}</span>{link}</div>')
    _md(f'<div class="sig-panel">{"".join(rows)}</div>')
