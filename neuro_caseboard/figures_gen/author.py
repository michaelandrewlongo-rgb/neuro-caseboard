"""Figure-spec author — `CaseContext` -> structured `FigureSpec`s (LOOP_PROMPT §2).

LLM-first (injected `complete_fn`, mirroring the Explorer / intake / case author) with a grounded,
topic-agnostic deterministic fallback. The deterministic path picks an archetype from
`classify_profile(case.to_topic())` and lays out well-spaced, case-aligned nodes (side/level/target
come straight from the case) — no hardcoded clinical content. The guard (`guard.py`) then drops any
spec that contradicts the case before rendering.
"""

from __future__ import annotations

import json
import os

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.figures_gen.spec import FigureSpec
from neuro_caseboard.explore_llm import _extract_json, _default_complete, llm_available

_MAX_SPECS = 4

FIGSPEC_SYSTEM = """You are a neurosurgical attending designing 2-4 CASE SCHEMATICS to help \
conceptualize ONE specific operation. For each, output a STRUCTURED figure spec (not an image): an \
archetype, labeled nodes with normalized x/y in [0,1], spatial relations, the side/level/region, and \
short callouts. Keep every element specific to THIS case; never depict a different side/level/region. \
Archetypes: "corridor" (approach trajectory), "spine_level" (vertebral level + approach), \
"vessel_config" (parent vessel + lesion), "anatomy_map" (structures at risk).

Output ONLY JSON:
{"figures":[{"archetype":"...","title":"...","side":"left|right|bilateral|midline|","level":"...",
"region":"...","nodes":[{"id":"n1","label":"...","x":0.2,"y":0.5,"kind":"target|corridor|vessel|structure"}],
"edges":[{"src":"n1","dst":"n2","kind":"approach|trajectory|relation"}],"callouts":["..."],
"caption":"Schematic (not a radiograph): ..."}]}"""


def _figspec_user(case: CaseContext) -> str:
    fields = [(k, v) for k, v in (
        ("laterality", case.laterality), ("level", case.level), ("location", case.location),
        ("pathology", case.pathology), ("procedure", case.procedure),
        ("surgical_goal", case.surgical_goal)) if v]
    return "CASE:\n" + "\n".join(f"- {k}: {v}" for k, v in fields)


def _coerce_specs(raw: dict) -> list[FigureSpec]:
    specs = []
    for item in (raw.get("figures") or [])[: _MAX_SPECS]:
        if isinstance(item, dict):
            specs.append(FigureSpec.from_dict(item))
    return specs


def _archetype_for(profile: str) -> str:
    # The approach schematic defaults to a corridor diagram (a generic cranial/other approach is a
    # corridor); spine and vascular get their specialized archetypes.
    return {"spine": "spine_level", "vascular": "vessel_config"}.get(profile, "corridor")


def _region_for(profile: str) -> str:
    return {"spine": "spine", "vascular": "cerebrovascular",
            "skull_base": "cranial"}.get(profile, "cranial" if profile else "")


def deterministic_figure_specs(case: CaseContext) -> list[FigureSpec]:
    """Two grounded schematics: an approach/corridor diagram (profile archetype) and an
    anatomy-at-risk map. Nodes are well-spaced and labeled from the case's own geometry."""
    from neuro_caseboard.pipeline import classify_profile
    profile = classify_profile(case.to_topic())
    arch = _archetype_for(profile)
    region = _region_for(profile)
    side = case.laterality
    target = case.target() or "operative target"
    topic = case.to_topic()
    side_label = f"{side} approach" if side else "approach corridor"

    from neuro_caseboard.figures_gen.spec import FigureNode, FigureEdge
    approach = FigureSpec(
        archetype=arch, title=f"{topic} — approach", side=side, level=case.level, region=region,
        nodes=[  # well-spaced to avoid label collisions
            FigureNode(id="approach", label=side_label, x=0.16, y=0.40, kind="corridor"),
            FigureNode(id="target", label=target, x=0.50, y=0.40, kind="target"),
            FigureNode(id="risk", label="structure to preserve", x=0.80, y=0.62, kind="structure"),
        ],
        edges=[FigureEdge("approach", "target", "approach"),
               FigureEdge("target", "risk", "relation")],
        callouts=[f"goal: {case.surgical_goal}" if case.surgical_goal else "confirm operative goal",
                  "structures to preserve along the corridor"],
        caption=f"Schematic (not a radiograph): operative corridor to {target}.")

    amap = FigureSpec(
        archetype="anatomy_map", title=f"{topic} — anatomy at risk", side=side, level=case.level,
        region=region,
        nodes=[
            FigureNode(id="t", label=target, x=0.50, y=0.46, kind="target"),
            FigureNode(id="s1", label="structure at risk (medial)", x=0.22, y=0.28, kind="structure"),
            FigureNode(id="s2", label="structure at risk (lateral)", x=0.80, y=0.30, kind="structure"),
            FigureNode(id="s3", label="vascular structure", x=0.50, y=0.80, kind="vessel"),
        ],
        edges=[FigureEdge("t", "s1", "relation"), FigureEdge("t", "s2", "relation"),
               FigureEdge("t", "s3", "relation")],
        callouts=["identify and protect each labeled structure",
                  "confirm orientation against intra-op landmarks"],
        caption=f"Schematic (not a radiograph): structures around {target}.")
    return [approach, amap]


def _provider_complete():
    if os.environ.get("CASEBOARD_LLM", "1") == "0":
        return None
    if not llm_available():
        return None
    return lambda system, user: _default_complete(system, user, temperature=0.2)


def build_figure_specs(case: CaseContext, *, complete_fn=None, max_specs: int = _MAX_SPECS):
    """Author up to `max_specs` figure specs. LLM-first (injected `complete_fn` or a configured
    provider); on no-provider / underproduction / any failure, the deterministic fallback."""
    fn = complete_fn or _provider_complete()
    if fn is None:
        return deterministic_figure_specs(case)[:max_specs]
    try:
        specs = _coerce_specs(json.loads(_extract_json(fn(FIGSPEC_SYSTEM, _figspec_user(case)))))
        if not specs:
            return deterministic_figure_specs(case)[:max_specs]
        return specs[:max_specs]
    except Exception:
        return deterministic_figure_specs(case)[:max_specs]
