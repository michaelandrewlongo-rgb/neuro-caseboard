"""Typed contract for the Operative Briefing Bundle (Pydantic v2).

Separate from neuro_caseboard.model.Dossier — that model stays the evidence-audit shape.
This is the one-page-briefing contract: serializes cleanly through FastAPI and feeds the
generated TypeScript types. The embedded CaseContext and Dossier are dataclasses (untouched),
so they ride along as arbitrary types with field serializers.
"""
from __future__ import annotations

import dataclasses
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

BRIEFING_SCHEMA_VERSION = 1


class BriefingItem(BaseModel):
    text: str
    priority: Literal["critical", "high", "optional"] = "high"
    source_refs: list[str] = []      # ["T1","L2"] — the hidden claim→source map
    unsupported: bool = False        # clinician-verify; never silently dropped


class BriefingSection(BaseModel):
    key: str
    title: str
    items: list[BriefingItem] = []
    note: str = ""


class TreatmentModality(BaseModel):
    name: str
    role: str = ""
    advantages: list[str] = []
    limitations: list[str] = []
    favoring: list[str] = []
    preferred: bool = False
    source_refs: list[str] = []


class AlgoNode(BaseModel):
    id: str
    label: str
    kind: Literal["decision", "action", "terminal"] = "decision"


class AlgoEdge(BaseModel):
    src: str
    dst: str
    condition: str = ""


class DecisionAlgorithm(BaseModel):
    nodes: list[AlgoNode] = []
    edges: list[AlgoEdge] = []


class CranialEquipment(BaseModel):
    kind: Literal["cranial"] = "cranial"
    head_fixation: list[str] = []
    visualization_navigation: list[str] = []
    monitoring: list[str] = []
    instruments_clips: list[str] = []
    graft_reconstruction: list[str] = []
    contingency: list[str] = []
    source_refs: list[str] = []


class SpineEquipment(BaseModel):
    kind: Literal["spine"] = "spine"
    positioning_monitoring: list[str] = []
    decompression_fusion_tools: list[str] = []
    instrumentation_system: list[str] = []
    cage_class_sizing: list[str] = []
    graft_options: list[str] = []
    navigation_robotics_fluoro: list[str] = []
    backup_salvage: list[str] = []
    source_refs: list[str] = []


class EndovascularEquipment(BaseModel):
    kind: Literal["endovascular"] = "endovascular"
    access_strategy: list[str] = []
    catheters_wires: list[str] = []
    devices: list[str] = []
    antithrombotic: list[str] = []
    closure: list[str] = []
    bailout_access_alt: list[str] = []
    source_refs: list[str] = []


EquipmentPlan = Annotated[
    CranialEquipment | SpineEquipment | EndovascularEquipment,
    Field(discriminator="kind"),
]


class BriefingFigure(BaseModel):
    fig_id: str
    image_path: str
    caption: str = ""
    citation: str = ""
    intent: str = ""            # pathology|anatomy|technique|device
    generated: bool = False     # schematic — excluded from the 5–10 textbook target
    source_n: str = ""          # T# ref


class BriefingReference(BaseModel):
    ref_id: str                 # "T1" | "L1"
    kind: Literal["textbook", "pubmed"]
    citation: str
    meta: dict = {}
    sections: list[str] = []    # section keys it supports (the support map)


class OperativeBriefing(BaseModel):
    title: str
    sections: list[BriefingSection] = []
    algorithm: DecisionAlgorithm | None = None
    modalities: list[TreatmentModality] = []
    equipment: EquipmentPlan | None = None
    unknowns: list[str] = []
    disclaimer: str = ""


class BriefingProvenance(BaseModel):
    textbook_ok: bool = True
    literature_ok: bool = True
    degraded: bool = False
    reason: str = ""
    failed_sections: list[str] = []
    model: str = ""


def _to_jsonable(v: Any) -> Any:
    # ponytail: dataclasses ride along as arbitrary types; asdict is the one conversion needed.
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return dataclasses.asdict(v)
    return v


class OperativeBriefingBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: Literal["briefing"] = "briefing"
    schema_version: int = BRIEFING_SCHEMA_VERSION
    topic: str = ""
    case: Any = None            # CaseContext dataclass (or dict in tests)
    briefing: OperativeBriefing
    figures: list[BriefingFigure] = []
    references: list[BriefingReference] = []
    dossier: Any = None         # neuro_caseboard.model.Dossier dataclass (full audit)
    provenance: BriefingProvenance

    @field_serializer("case", "dossier")
    def _ser(self, v: Any, _info):
        return _to_jsonable(v)
