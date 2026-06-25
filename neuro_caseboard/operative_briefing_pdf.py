"""Operative Briefing Bundle PDF — render an OperativeBriefingBundle (Plan 1) to A4.

Three surfaces, hard-separated: page 1 is a citation-free, figure-free operative briefing
held to <=2 pages by a fit ladder; then a figure atlas; then a references/evidence page.
Signal print identity via exec_navy tokens. Pure HTML/SVG builders test offline; the
Chromium orchestrator supplies the authoritative page-count measure (render -> pypdf).
"""
from __future__ import annotations

import html
import io
import os
from dataclasses import dataclass, field

import pypdf

from neuro_caseboard.exec_navy import PRINT_TOKENS, SIGNAL_TOKENS


def count_pdf_pages(data: bytes) -> int:
    """Authoritative page count of a rendered PDF (what pagination actually produced)."""
    return len(pypdf.PdfReader(io.BytesIO(data)).pages)


def _tokens(theme: str) -> str:
    return PRINT_TOKENS if theme == "print" else SIGNAL_TOKENS


def _clip(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


# --- decision-algorithm SVG (deterministic, theme-token colors) --------------------
# Colors via a <style> block + classes — var() does NOT resolve in SVG presentation
# attributes, only in CSS (advisor).
_ALGO_CSS = """
  .n{ rx:5; ry:5; stroke:var(--line); stroke-width:1; }
  .n.decision{ fill:var(--panel); stroke:var(--accent); }
  .n.action{ fill:var(--panel); }
  .n.terminal{ fill:var(--panel); stroke:var(--supported); }
  .nt{ font-family:var(--ui); font-size:8.5pt; fill:var(--ink); }
  .e{ stroke:var(--line); stroke-width:1.2; marker-end:url(#arrow); fill:none; }
  .ec{ font-family:var(--mono); font-size:7pt; fill:var(--accent); }
"""


def _algo_layers(nodes, edges):
    """Longest-path layering (layer = max(layer of preds)+1). Insertion order on cycle."""
    ids = [n.id for n in nodes]
    preds = {i: [] for i in ids}
    for e in edges:
        preds[e.dst].append(e.src)
    layer = {i: 0 for i in ids}
    for _ in range(len(ids)):                 # relax |V| times; no-progress => settled
        changed = False
        for i in ids:
            want = max((layer[p] + 1 for p in preds[i]), default=0)
            if want > layer[i]:
                layer[i] = want
                changed = True
        if not changed:
            break
    else:
        # never converged within |V| passes -> cycle; degrade to insertion order
        layer = {i: idx for idx, i in enumerate(ids)}
    return layer


def build_algorithm_svg(algo, theme: str = "signal") -> str:
    if algo is None or not algo.nodes:
        return ""
    nodes = list(algo.nodes)
    ids = {n.id for n in nodes}
    edges = [e for e in algo.edges if e.src in ids and e.dst in ids]   # drop dangling
    layer = _algo_layers(nodes, edges)

    rows: dict[int, list] = {}
    for n in nodes:
        rows.setdefault(layer[n.id], []).append(n)

    BW, BH, HGAP, VGAP, PAD = 150, 34, 24, 28, 12
    ncols = max((len(r) for r in rows.values()), default=1)
    width = PAD * 2 + ncols * BW + (ncols - 1) * HGAP
    nlayers = max(rows) + 1 if rows else 1
    height = PAD * 2 + nlayers * BH + (nlayers - 1) * VGAP

    pos = {}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'width="100%" style="max-width:{width}px">',
             f'<style>{_ALGO_CSS}</style>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
             'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0 0 L10 5 L0 10 z" style="fill:var(--line)"/></marker></defs>']
    for ly in sorted(rows):
        row = rows[ly]
        span = len(row) * BW + (len(row) - 1) * HGAP
        x0 = (width - span) / 2
        y = PAD + ly * (BH + VGAP)
        for j, n in enumerate(row):
            x = x0 + j * (BW + HGAP)
            pos[n.id] = (x + BW / 2, y, y + BH)            # cx, top, bottom
            kind = n.kind if n.kind in ("decision", "action", "terminal") else "decision"
            parts.append(f'<rect class="n {kind}" x="{x:.1f}" y="{y:.1f}" '
                         f'width="{BW}" height="{BH}"/>')
            parts.append(f'<text class="nt" x="{x + BW / 2:.1f}" y="{y + BH / 2 + 3:.1f}" '
                         f'text-anchor="middle">{html.escape(_clip(n.label, 26))}</text>')
    for e in edges:
        sx, _, sb = pos[e.src]
        dx, dt_, _ = pos[e.dst]
        parts.append(f'<line class="e" x1="{sx:.1f}" y1="{sb:.1f}" x2="{dx:.1f}" y2="{dt_:.1f}"/>')
        if e.condition:
            mx, my = (sx + dx) / 2, (sb + dt_) / 2
            parts.append(f'<text class="ec" x="{mx:.1f}" y="{my:.1f}" '
                         f'text-anchor="middle">{html.escape(e.condition)}</text>')
    parts.append("</svg>")
    return "".join(parts)


# --- page 1: body + self-contained, font-scalable CSS ------------------------------
# Colors/fonts come from :root tokens (exec_navy); every text size is calc(var(--fs)*Npt)
# so the fit ladder's --fs actually shrinks it. We do NOT reuse _STRUCTURE_CSS's fixed-pt
# text classes — they'd win on specificity and the shrink rung would no-op (advisor).
_BRIEFING_PAGE_CSS = """
@page{ size:A4; margin:0; }
*{ box-sizing:border-box; }
html,body{ margin:0; background:var(--bg); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.bf-page{ color:var(--ink); font-family:var(--ui); padding:12mm 16mm 14mm; }
.bf-eyebrow{ font-family:var(--mono); font-size:calc(var(--fs)*7pt); font-weight:700;
  letter-spacing:.2em; text-transform:uppercase; color:var(--accent); }
.bf-title{ font-family:var(--ui); font-weight:700; font-size:calc(var(--fs)*19pt);
  letter-spacing:-.02em; line-height:1.1; margin:2mm 0 4mm; }
.bf-sec{ margin-top:calc(var(--fs)*5mm); break-inside:avoid; }
.bf-sec-h{ font-family:var(--ui); font-weight:700; font-size:calc(var(--fs)*11pt);
  color:var(--ink); border-top:1px solid var(--line); padding-top:2mm; margin-bottom:1.5mm; }
.bf-item{ font-family:var(--read); font-size:calc(var(--fs)*10pt); line-height:1.4;
  color:var(--ink); margin:0 0 1.4mm; padding-left:4mm; text-indent:-4mm; }
.bf-item::before{ content:"\\2014"; color:var(--accent); margin-right:2mm; }
.bf-item.unsupported::after{ content:" \\2014 clinician-verify"; color:var(--verify);
  font-family:var(--mono); font-size:calc(var(--fs)*7pt); text-transform:uppercase;
  letter-spacing:.06em; }
.bf-note{ font-family:var(--read); font-style:italic; font-size:calc(var(--fs)*9pt);
  color:var(--muted); margin:1mm 0 0; }
.bf-mods{ display:flex; flex-wrap:wrap; gap:3mm; margin-top:2mm; }
.bf-mod{ flex:1 1 46%; border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:var(--radius); padding:2.5mm 3mm; background:var(--panel); break-inside:avoid; }
.bf-mod.pref{ border-left-color:var(--supported); }
.bf-mod .nm{ font-family:var(--ui); font-weight:700; font-size:calc(var(--fs)*9.5pt); color:var(--ink); }
.bf-mod .ro{ font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--muted); margin:.6mm 0; }
.bf-mod ul{ margin:.6mm 0 0; padding-left:4mm; }
.bf-mod li{ font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--ink); }
.bf-eq{ border:1px solid var(--line); border-radius:var(--radius); padding:2.5mm 3mm;
  background:var(--panel); margin-top:2mm; break-inside:avoid; }
.bf-eq-kind{ font-family:var(--mono); font-size:calc(var(--fs)*7pt); font-weight:700;
  letter-spacing:.12em; text-transform:uppercase; color:var(--accent); margin-bottom:1mm; }
.bf-eq-row{ display:flex; gap:3mm; margin:.5mm 0; }
.bf-eq-k{ flex:0 0 38mm; font-family:var(--ui); font-weight:600;
  font-size:calc(var(--fs)*8.5pt); color:var(--muted); }
.bf-eq-v{ flex:1; font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--ink); }
.bf-algo{ margin:2mm 0; }
.bf-unknowns{ font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--muted);
  border-left:3px solid var(--verify); padding-left:3mm; margin-top:3mm; }
.bf-disc{ font-family:var(--mono); font-size:calc(var(--fs)*7pt); color:var(--faint);
  margin-top:4mm; padding-top:2mm; border-top:1px solid var(--line); }
"""


def _esc(s: str) -> str:
    return html.escape(s or "")


def _items_html(items, drop) -> str:
    out = []
    for it in items:
        if it.priority in drop:
            continue
        cls = "bf-item unsupported" if it.unsupported else "bf-item"
        out.append(f'<div class="{cls}">{_esc(it.text)}</div>')   # NB: source_refs NOT rendered
    return "".join(out)


def _modalities_html(mods) -> str:
    if not mods:
        return ""
    cards = []
    for m in mods:
        pref = " pref" if m.preferred else ""
        adv = "".join(f"<li>+ {_esc(a)}</li>" for a in m.advantages)
        lim = "".join(f"<li>− {_esc(x)}</li>" for x in m.limitations)
        ro = f'<div class="ro">{_esc(m.role)}</div>' if m.role else ""
        cards.append(f'<div class="bf-mod{pref}"><div class="nm">{_esc(m.name)}</div>{ro}'
                     f'<ul>{adv}{lim}</ul></div>')
    return f'<div class="bf-mods">{"".join(cards)}</div>'


def _equipment_html(equip) -> str:
    """Generic: one renderer for all three subspecialty schemas (advisor)."""
    if equip is None:
        return ""
    data = equip.model_dump()
    kind = data.pop("kind", "")
    data.pop("source_refs", None)
    rows = []
    for field_name, vals in data.items():
        if not vals:
            continue
        label = field_name.replace("_", " ").title()
        rows.append(f'<div class="bf-eq-row"><span class="bf-eq-k">{_esc(label)}</span>'
                    f'<span class="bf-eq-v">{_esc("; ".join(vals))}</span></div>')
    if not rows:
        return ""
    return (f'<div class="bf-eq"><div class="bf-eq-kind">{_esc(kind)} setup</div>'
            f'{"".join(rows)}</div>')


def _page1_body(briefing, *, drop: tuple = ()) -> str:
    out = ['<div class="bf-eyebrow">Operative Briefing</div>',
           f'<div class="bf-title">{_esc(briefing.title)}</div>']
    for sec in briefing.sections:
        items = _items_html(sec.items, drop)
        if not items and not sec.note:
            continue
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">{_esc(sec.title)}</div>{items}')
        if sec.note:
            out.append(f'<div class="bf-note">{_esc(sec.note)}</div>')
        out.append("</div>")
    svg = build_algorithm_svg(briefing.algorithm)
    if svg:
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">Decision algorithm</div>'
                   f'<div class="bf-algo">{svg}</div></div>')
    mods = _modalities_html(briefing.modalities)
    if mods:
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">Treatment options</div>{mods}</div>')
    eq = _equipment_html(briefing.equipment)
    if eq:
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">Equipment</div>{eq}</div>')
    if briefing.unknowns:
        items = " · ".join(_esc(u) for u in briefing.unknowns)
        out.append(f'<div class="bf-unknowns"><b>Case-specific unknowns:</b> {items}</div>')
    if briefing.disclaimer:
        out.append(f'<div class="bf-disc">{_esc(briefing.disclaimer)}</div>')
    return "".join(out)


def build_briefing_page_html(briefing, *, fs: float = 1.0, drop: tuple = (),
                             theme: str = "signal") -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            f"{_tokens(theme)}{_BRIEFING_PAGE_CSS}</style></head><body>"
            f'<div class="bf-page" style="--fs:{fs}">{_page1_body(briefing, drop=drop)}</div>'
            "</body></html>")


# --- fit ladder: shrink -> trim -> compress -> allow page 2 (<=2 pages, always) -----
@dataclass
class FitResult:
    fragment: str
    fs: float
    drop: tuple = ()
    pages: int = 1
    rungs: list = field(default_factory=list)


def fit_briefing_page(briefing, measure, *, theme: str = "signal", compress=None,
                      fs_steps=(1.0, 0.95, 0.9, 0.85, 0.82)) -> FitResult:
    """Drive the briefing to <=2 pages. `measure(standalone_doc) -> page_count` is injected
    (real = render+pypdf; tests = fake). `compress(briefing) -> briefing` is optional."""
    floor = fs_steps[-1]
    rungs: list = []

    def attempt(b, fs, drop):
        doc = build_briefing_page_html(b, fs=fs, drop=drop, theme=theme)
        return measure(doc)

    def result(b, fs, drop, pages, tag):
        return FitResult(_page1_body(b, drop=drop), fs, drop, pages, rungs + [tag])

    # rung 1 — shrink font at full content, target 1 page
    for fs in fs_steps:
        pages = attempt(briefing, fs, ())
        if pages <= 1:
            return result(briefing, fs, (), pages, f"shrink:{fs}")
    rungs.append("shrink:floor")

    # rung 2 — trim optional at floor, target 1
    pages = attempt(briefing, floor, ("optional",))
    if pages <= 1:
        return result(briefing, floor, ("optional",), pages, "trim:optional")

    # rung 3 — one compress pass, then retry shrink + trim-optional, target 1
    b = briefing
    if compress is not None:
        try:
            b = compress(briefing)
            rungs.append("compress")
        except Exception:
            b = briefing
            rungs.append("compress:failed")
        for fs in fs_steps:
            pages = attempt(b, fs, ())
            if pages <= 1:
                return result(b, fs, (), pages, f"shrink2:{fs}")
        pages = attempt(b, floor, ("optional",))
        if pages <= 1:
            return result(b, floor, ("optional",), pages, "trim2:optional")

    # rung 4 — allow page 2; drop optional, then optional+high, until <=2 (critical never)
    for drop in (("optional",), ("optional", "high")):
        pages = attempt(b, floor, drop)
        if pages <= 2:
            return result(b, floor, drop, pages, "page2:" + "+".join(drop))
    # ponytail: critical-only at the legibility floor is the mechanical ceiling; accept it,
    # no export-error state (spec §2/§7). Add a hard under-floor only if real briefings ever
    # exceed this — they don't (critical core is small).
    pages = attempt(b, floor, ("optional", "high"))
    return result(b, floor, ("optional", "high"), pages, "page2:critical-only")


# --- figure atlas + references page (separate pages, after the briefing) -----------
# Atlas/refs get their own additive CSS so they stay independent of the page-1 scalable
# block. Figures are break-inside:avoid with a max-height so 1–2 land per page by aspect.
_ATLAS_CSS = """
.bf-break{ break-before:page; }
.bf-page-h{ font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.2em;
  text-transform:uppercase; color:var(--accent); padding:12mm 16mm 0; }
.bf-atlas{ padding:3mm 16mm 0; }
.bf-fig{ break-inside:avoid; margin:0 0 5mm; border:1px solid var(--line);
  border-radius:var(--radius); overflow:hidden; background:var(--panel); }
.bf-fig img{ display:block; width:100%; max-height:118mm; object-fit:contain;
  border-bottom:1px solid var(--line); }
.bf-fig figcaption{ padding:3mm 4mm; font-family:var(--read); font-size:9.5pt; line-height:1.4;
  color:var(--muted); }
.bf-fig .fid{ font-family:var(--mono); font-size:7pt; font-weight:700; color:var(--accent);
  margin-right:2mm; }
.bf-fig .src{ display:block; margin-top:1.2mm; color:var(--faint); }
.bf-refs{ padding:3mm 16mm 14mm; }
.bf-refs h3{ font-family:var(--ui); font-weight:700; font-size:11pt; color:var(--ink);
  border-top:1px solid var(--line); padding-top:2mm; margin:5mm 0 2mm; }
.bf-ref{ font-family:var(--read); font-size:9pt; color:var(--ink); margin:0 0 1.6mm;
  padding-left:9mm; text-indent:-9mm; }
.bf-ref .rid{ font-family:var(--mono); font-size:7.5pt; font-weight:700; color:var(--accent);
  margin-right:2mm; }
.bf-ref .map{ display:block; font-family:var(--mono); font-size:6.6pt; color:var(--muted);
  text-transform:uppercase; letter-spacing:.08em; text-indent:0; }
"""


def _figure_html(fig) -> str:
    from neuro_caseboard.exec_navy import img_data_uri
    try:
        img = f'<img src="{img_data_uri(fig.image_path)}">'
    except Exception:
        img = ""                                         # never emit a broken image; keep caption
    src_bits = " · ".join(p for p in (fig.citation, fig.source_n, fig.intent) if p)
    src = f'<span class="src">{_esc(src_bits)}</span>' if src_bits else ""
    return (f'<figure class="bf-fig">{img}<figcaption>'
            f'<span class="fid">{_esc(fig.fig_id)}</span>{_esc(fig.caption)}{src}'
            f'</figcaption></figure>')


def build_figure_atlas_html(figures, theme: str = "signal") -> str:
    if not figures:
        return ""
    figs = "".join(_figure_html(f) for f in figures)
    return ('<div class="bf-break"></div>'
            '<div class="bf-page-h">Figure Atlas — high-yield plates</div>'
            f'<div class="bf-atlas">{figs}</div>')


def _ref_html(ref) -> str:
    mapline = ""
    if ref.sections:
        mapline = f'<span class="map">supports: {_esc(", ".join(ref.sections))}</span>'
    extra = ""
    for k in ("pmid", "doi", "url", "page", "book"):
        v = (ref.meta or {}).get(k)
        if v:
            extra += f" · {_esc(str(v))}"
    return (f'<div class="bf-ref"><span class="rid">{_esc(ref.ref_id)}</span>'
            f'{_esc(ref.citation)}{extra}{mapline}</div>')


def build_references_html(references, theme: str = "signal") -> str:
    if not references:
        return ""
    tb = [r for r in references if r.kind == "textbook"]
    lit = [r for r in references if r.kind == "pubmed"]
    out = ['<div class="bf-break"></div>',
           '<div class="bf-page-h">References &amp; Evidence</div>',
           '<div class="bf-refs">']
    if tb:
        out.append("<h3>Textbook sources</h3>")
        out.extend(_ref_html(r) for r in tb)
    if lit:
        out.append("<h3>Contemporary Literature</h3>")
        out.extend(_ref_html(r) for r in lit)
    out.append("</div>")
    return "".join(out)


# --- full-doc assembly + Chromium orchestrator + LLM-compress factory --------------
_PDF_MARGIN = {"top": "0", "bottom": "0", "left": "0", "right": "0"}


def _assemble_full_doc(page1_fragment: str, atlas_body: str, refs_body: str, *,
                       fs: float, theme: str, title: str, topic: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{_esc(title)}</title><style>"
            f"{_tokens(theme)}{_BRIEFING_PAGE_CSS}{_ATLAS_CSS}</style></head><body>"
            f'<div class="bf-page" style="--fs:{fs}">{page1_fragment}</div>'
            f"{atlas_body}{refs_body}</body></html>")


def _make_compress(synth_client):
    """Return compress(briefing)->tightened copy, or None when no client (ladder skips rung 3)."""
    if synth_client is None:
        return None

    def compress(briefing):
        flat = [(si, ii) for si, sec in enumerate(briefing.sections)
                for ii, _ in enumerate(sec.items)]
        if not flat:
            return briefing
        lines = [briefing.sections[si].items[ii].text for si, ii in flat]
        system = ("You tighten operative-briefing bullet lines. Rewrite each numbered line "
                  "more concisely. Preserve every clinical fact, number, device, and dose. "
                  "Add nothing. Output exactly one rewritten line per input line, same order, "
                  "no numbering.")
        user = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(lines))
        try:
            out = synth_client.generate(system, user, [])
        except Exception:
            return briefing
        new = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
        if len(new) != len(lines):
            return briefing                       # shape mismatch -> don't risk dropping facts
        copy = briefing.model_copy(deep=True)
        for (si, ii), txt in zip(flat, new):
            copy.sections[si].items[ii].text = txt
        return copy

    return compress


def render_operative_briefing_pdf(bundle, out_path, *, theme: str | None = None,
                                  synth_client=None) -> str:
    """Render the bundle to an A4 PDF at out_path. Requires the `briefing` extra + Chromium."""
    if theme is None:
        theme = os.environ.get("CASEBOARD_PDF_STYLE", "signal")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:                          # ImportError, or None injected in tests
        raise RuntimeError(
            "renderer unavailable: the operative-briefing PDF needs the `briefing` extra "
            "(Playwright + a Chromium binary)") from e
    if sync_playwright is None:
        raise RuntimeError("renderer unavailable: Playwright not importable")

    briefing = bundle.briefing
    title = getattr(briefing, "title", "") or getattr(bundle, "topic", "")
    atlas = build_figure_atlas_html(getattr(bundle, "figures", []) or [], theme)
    refs = build_references_html(getattr(bundle, "references", []) or [], theme)
    compress = _make_compress(synth_client)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def measure(doc: str) -> int:
            page.set_content(doc, wait_until="load")
            data = page.pdf(format="A4", print_background=True, margin=_PDF_MARGIN)
            return count_pdf_pages(data)

        fit = fit_briefing_page(briefing, measure, theme=theme, compress=compress)
        doc = _assemble_full_doc(fit.fragment, atlas, refs, fs=fit.fs, theme=theme,
                                 title=title, topic=getattr(bundle, "topic", ""))
        page.set_content(doc, wait_until="networkidle")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.pdf(path=str(out_path), format="A4", print_background=True, margin=_PDF_MARGIN)
        browser.close()
    return str(out_path)
