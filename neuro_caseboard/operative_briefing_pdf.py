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
