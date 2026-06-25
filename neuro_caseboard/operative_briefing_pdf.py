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
