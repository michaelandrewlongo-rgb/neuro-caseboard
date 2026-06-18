"""Generated case schematics (WS-4): a structured figure-spec author + a deterministic renderer +
an anti-bleed guard.

`generate_case_figures` is the end-to-end entry point: author specs from a `CaseContext`, drop any
that contradict the case (guard), render each to a deterministic PNG, and return them as
`FigureItem`s captioned as schematics (never radiographs) for attachment to the dossier.
"""

from __future__ import annotations

from pathlib import Path

from neuro_caseboard.model import FigureItem
from neuro_caseboard.figures_gen.author import build_figure_specs, deterministic_figure_specs  # noqa: F401
from neuro_caseboard.figures_gen.guard import guard_spec, filter_specs  # noqa: F401
from neuro_caseboard.figures_gen.render import render_spec_to_file
from neuro_caseboard.figures_gen.spec import FigureSpec  # noqa: F401

_SCHEMATIC_PREFIX = "Schematic (not a radiograph)"


def _caption(spec) -> str:
    cap = (spec.caption or "").strip()
    if cap.lower().startswith("schematic"):
        return cap
    title = spec.title or "case schematic"
    return f"{_SCHEMATIC_PREFIX}: {title}." if not cap else f"{_SCHEMATIC_PREFIX}: {cap}"


def generate_case_figures(case, out_dir, *, complete_fn=None, figret=None,
                          start_index: int = 1) -> list:
    """Author -> guard -> render case figures; return `FigureItem`s.

    Deterministic and offline by default (PIL core dep). `complete_fn` injects the LLM author for
    tests / live use; without it the deterministic author is used. Specs that contradict the case
    (wrong side/level/region) are dropped by the guard and never rendered.

    WS-4: when a figure retriever (`figret`) is available, the abstract `anatomy_map` schematic is
    replaced by an annotated crop of a RETRIEVED real textbook plate (guard-checked, labeled as a
    reference image). With no figret the `anatomy_map` falls back to its deterministic schematic and
    the corridor schematic is byte-identical to before.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    specs = filter_specs(build_figure_specs(case, complete_fn=complete_fn), case)
    items: list[FigureItem] = []
    i = start_index
    for spec in specs:
        if spec.archetype == "anatomy_map" and figret is not None:
            from neuro_caseboard.figures_gen.plate import build_plate_figure
            plate = build_plate_figure(case, figret, out, i)
            if plate is not None:
                items.append(plate)
                i += 1
                continue                               # retrieved plate replaces the schematic
        path = out / f"case-fig-{i:02d}.png"
        render_spec_to_file(spec, path)                # deterministic schematic (corridor frozen)
        items.append(FigureItem(
            fig_id=f"S{i}",
            image_path=str(path),
            caption=_caption(spec),
            citation="generated schematic",
            relevance=(f"Case-specific schematic — {spec.archetype.replace('_', ' ')}"
                       + (f", {spec.side} side" if spec.side else "")
                       + (f", level {spec.level}" if spec.level else "")),
        ))
        i += 1
    return items
