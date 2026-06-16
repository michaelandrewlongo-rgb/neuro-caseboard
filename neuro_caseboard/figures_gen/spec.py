"""The structured figure spec — the contract between the (LLM or deterministic) author and the
deterministic renderer (LOOP_PROMPT §2).

An author proposes a `FigureSpec` (archetype + labeled nodes + spatial relations + side/level/region
+ callouts) as plain data; `render.py` turns it into a labeled schematic with deterministic Python
drawing code. The pixels are a pure function of this spec — no text-to-image, no hallucinated
photoreal anatomy. `from_dict` tolerates messy model JSON (clamps coordinates, drops malformed
nodes, defaults the archetype).
"""

from __future__ import annotations

from dataclasses import dataclass, field

ARCHETYPES = {"corridor", "spine_level", "vessel_config", "anatomy_map"}
_DEFAULT_ARCHETYPE = "anatomy_map"
_EDGE_KINDS = {"relation", "trajectory", "approach"}


def _clamp01(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return 0.0 if f < 0.0 else 1.0 if f > 1.0 else f


@dataclass
class FigureNode:
    id: str
    label: str
    x: float = 0.5
    y: float = 0.5
    kind: str = "structure"        # structure | target | corridor | vessel | level | callout


@dataclass
class FigureEdge:
    src: str
    dst: str
    kind: str = "relation"         # relation | trajectory | approach


@dataclass
class FigureSpec:
    archetype: str = _DEFAULT_ARCHETYPE
    title: str = ""
    side: str = ""                 # left | right | bilateral | midline | ""
    level: str = ""                # spine-level token or ""
    region: str = ""               # generalizable region label (cervical spine, frontal, cpa, mca…)
    nodes: list[FigureNode] = field(default_factory=list)
    edges: list[FigureEdge] = field(default_factory=list)
    callouts: list[str] = field(default_factory=list)
    caption: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "FigureSpec":
        d = d or {}
        archetype = str(d.get("archetype", "")).strip()
        if archetype not in ARCHETYPES:
            archetype = _DEFAULT_ARCHETYPE

        nodes: list[FigureNode] = []
        for raw in d.get("nodes", []) or []:
            if not isinstance(raw, dict):
                continue
            nid = str(raw.get("id", "")).strip()
            label = str(raw.get("label", "")).strip()
            if not nid or not label:          # a node must be identifiable and labeled
                continue
            nodes.append(FigureNode(
                id=nid, label=label, x=_clamp01(raw.get("x", 0.5)),
                y=_clamp01(raw.get("y", 0.5)), kind=str(raw.get("kind", "structure")).strip()
                or "structure"))

        node_ids = {n.id for n in nodes}
        edges: list[FigureEdge] = []
        for raw in d.get("edges", []) or []:
            if not isinstance(raw, dict):
                continue
            src = str(raw.get("src", "")).strip()
            dst = str(raw.get("dst", "")).strip()
            if src not in node_ids or dst not in node_ids:   # dangling edge -> drop
                continue
            kind = str(raw.get("kind", "relation")).strip()
            edges.append(FigureEdge(src=src, dst=dst,
                                    kind=kind if kind in _EDGE_KINDS else "relation"))

        callouts = [str(c).strip() for c in (d.get("callouts") or []) if str(c).strip()]
        return cls(
            archetype=archetype, title=str(d.get("title", "")).strip(),
            side=str(d.get("side", "")).strip(), level=str(d.get("level", "")).strip(),
            region=str(d.get("region", "")).strip(), nodes=nodes, edges=edges,
            callouts=callouts, caption=str(d.get("caption", "")).strip())
