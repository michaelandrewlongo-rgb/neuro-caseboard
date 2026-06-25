from neuro_caseboard.briefing_model import (
    BRIEFING_SCHEMA_VERSION, BriefingItem, BriefingSection, TreatmentModality,
    DecisionAlgorithm, AlgoNode, AlgoEdge, CranialEquipment, SpineEquipment,
    EndovascularEquipment, BriefingFigure, BriefingReference, OperativeBriefing,
    BriefingProvenance, OperativeBriefingBundle,
)
import pydantic


def test_item_defaults_and_roundtrip():
    it = BriefingItem(text="secure ruptured aneurysm within 72h", source_refs=["T1", "L2"])
    assert it.priority == "high" and it.unsupported is False
    assert it.model_dump()["source_refs"] == ["T1", "L2"]


def test_equipment_discriminated_union_picks_class():
    # A dict tagged kind=spine must validate into SpineEquipment, never Cranial.
    brief = OperativeBriefing(
        title="x",
        equipment={"kind": "spine", "cage_class_sizing": ["PEEK 6mm"]},
    )
    assert isinstance(brief.equipment, SpineEquipment)
    assert brief.equipment.cage_class_sizing == ["PEEK 6mm"]


def test_bundle_schema_version_and_json_schema():
    b = OperativeBriefingBundle(
        topic="t", case={"any": "dict"}, briefing=OperativeBriefing(title="x"),
        dossier={"sections": []}, provenance=BriefingProvenance(),
    )
    assert b.schema_version == BRIEFING_SCHEMA_VERSION
    # JSON schema generation must not raise (drives TS codegen in a later plan).
    schema = OperativeBriefingBundle.model_json_schema()
    assert schema["properties"]["kind"]["default"] == "briefing"


def test_bundle_serializes_arbitrary_case_and_dossier():
    from dataclasses import dataclass
    @dataclass
    class FakeCase:
        procedure: str = "ACDF"
    b = OperativeBriefingBundle(
        topic="t", case=FakeCase(), briefing=OperativeBriefing(title="x"),
        dossier={"sections": []}, provenance=BriefingProvenance(),
    )
    dumped = b.model_dump(mode="json")
    assert dumped["case"]["procedure"] == "ACDF"
