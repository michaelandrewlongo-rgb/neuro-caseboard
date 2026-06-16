"""Anti-bleed guard for generated schematics (LOOP_PROMPT §6).

Rejects a `FigureSpec` whose **side**, **level**, or **region** contradicts the `CaseContext`, so a
schematic can never depict the wrong side/level or drift cross-region. Reuses the corpus figure
anti-bleed (`neuro_core.figure_guards.figure_offtarget` / `_levels_in`) for the region/level checks,
mirroring the retrieval lane's discipline. A rejected spec is dropped, never rendered.
"""

from __future__ import annotations

import re

_SIDES = {"left", "right"}


def _norm_level(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def guard_spec(spec, case) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means the spec contradicts the case and must be dropped."""
    # --- side ---
    cside = (case.laterality or "").strip().lower()
    sside = (spec.side or "").strip().lower()
    if cside in _SIDES and sside in _SIDES and cside != sside:
        return False, f"side mismatch: case is {cside}, spec is {sside}"

    # --- level (spine) ---
    if case.level and spec.level and _norm_level(case.level) != _norm_level(spec.level):
        try:
            from neuro_core.figure_guards import _levels_in
            shared = _levels_in(case.level) & _levels_in(spec.level)
        except Exception:
            shared = set()
        if not shared:
            return False, f"level mismatch: case is {case.level}, spec is {spec.level}"

    # --- region (cranial<->spine and finer divides) ---
    region_text = " ".join(p for p in (spec.region, spec.title, " ".join(spec.callouts)) if p)
    if region_text:
        try:
            from neuro_core.figure_guards import figure_offtarget
            if figure_offtarget(region_text, case.to_topic()):
                return False, f"region off-target for {case.to_topic()!r}: {spec.region!r}"
        except Exception:
            pass
    return True, ""


def filter_specs(specs, case):
    """Keep only the specs that pass `guard_spec` for this case."""
    return [s for s in specs if guard_spec(s, case)[0]]
