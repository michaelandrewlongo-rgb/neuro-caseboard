from caseprep.core.builder import _bind_prognostic_signs
from caseprep.core.contracts import ProvenanceRecord


def test_binds_thrombectomy_prognostic_signs_with_provenance():
    schema = {"procedure_family": {"id": "endovascular_thrombectomy"}, "case": {}}
    provenance: list[ProvenanceRecord] = []
    _bind_prognostic_signs(schema, provenance)

    block = schema["case"]["prognostic_signs"]
    assert block["favorable"] and block["unfavorable"]

    recs = [r for r in provenance if r.field_path == "case.prognostic_signs"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec.value_status == "generated"
    assert rec.generated_by == "caseprep.prognostic_signs"
    assert "hermes" in rec.source_ids  # union of cited pack ids


def test_no_binding_for_non_thrombectomy():
    schema = {"procedure_family": {"id": "spine_acdf"}, "case": {}}
    provenance: list[ProvenanceRecord] = []
    _bind_prognostic_signs(schema, provenance)
    assert "prognostic_signs" not in schema["case"]
    assert provenance == []
