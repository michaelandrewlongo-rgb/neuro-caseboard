"""WS-4 — the real-anatomy structures-at-risk figure: an annotated crop of a RETRIEVED textbook
plate, used in place of the abstract `anatomy_map` schematic when a figure corpus is available.

The plate is a labeled REFERENCE image (never the patient's own imaging) and is guarded against the
case: a plate whose region/level/side contradicts the case is rejected (reusing the schematic guard),
and the caller falls back to the deterministic schematic. PIL only — no new dependency. Offline-safe:
with no figure retriever this module is never reached.
"""

from __future__ import annotations

import re
from pathlib import Path

from neuro_caseboard.model import FigureItem
from neuro_caseboard.figures_gen.spec import FigureSpec
from neuro_caseboard.figures_gen.guard import guard_spec
from neuro_caseboard.figures_gen.render import render_plate

_REF_CAPTION = "Reference plate (not this patient's imaging)"
_LEVEL = re.compile(r"\b([CTLS]\d{1,2}(?:[-–]\s?[CTLS]?\d{1,2})?)\b", re.IGNORECASE)


def _first_level(text: str) -> str:
    m = _LEVEL.search(text or "")
    return m.group(1).upper().replace(" ", "") if m else ""


def _plate_spec_from_record(rec, case) -> FigureSpec:
    """A minimal FigureSpec carrying the plate's caption/region/level so the existing region/level
    guard (figure_offtarget / _levels_in) can reject a contradicting plate."""
    meta = getattr(rec, "metadata", {}) or {}
    cap = (meta.get("caption") or getattr(rec, "text", "") or "").strip()
    return FigureSpec(archetype="anatomy_map", title=cap[:80], side="",
                      level=_first_level(cap), region=cap, callouts=[cap], caption=cap)


def build_plate_figure(case, figret, out_dir, index: int, *, query=None) -> FigureItem | None:
    """Retrieve -> guard -> annotate a reference plate for the structures-at-risk map.

    Returns a `FigureItem` (reference-plate caption + corpus citation) for the first retrieved
    record with an existing image that passes the guard; returns ``None`` (caller falls back to the
    deterministic schematic) when there is no retriever, no record, a missing file, or every
    candidate is guard-rejected."""
    if figret is None:
        return None
    q = query or f"{case.to_topic()} anatomy structures at risk"
    try:
        recs = figret.retrieve(q, topic=case.to_topic(), top_n=4)
    except Exception:
        return None
    for rec in recs or []:
        meta = getattr(rec, "metadata", {}) or {}
        fp = meta.get("figure_path")
        if not fp or not Path(fp).exists():
            continue
        if not guard_spec(_plate_spec_from_record(rec, case), case)[0]:
            continue                                   # region/level/side contradicts the case
        cite = (meta.get("citation") or getattr(rec, "title", "") or "").strip()
        out_path = Path(out_dir) / f"case-fig-{index:02d}-plate.png"
        try:
            render_plate(fp, out_path, citation=cite)
        except Exception:
            return None
        return FigureItem(
            fig_id=f"P{index}",
            image_path=str(out_path),
            caption=f"{_REF_CAPTION}: {cite}" if cite else _REF_CAPTION,
            citation=cite or "retrieved reference plate",
            relevance=("Retrieved reference plate for the structures at risk"
                       + (f" — {case.target()}" if case.target() else "")),
        )
    return None
