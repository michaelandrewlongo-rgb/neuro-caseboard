from __future__ import annotations

from caseprep.evaluation.rubric import check_source_coverage
from caseprep.schema import _render_postop

FAMILY = "endovascular_thrombectomy"


def _schema(family=FAMILY):
    return {"procedure_family": {"id": family}}


def test_uncited_prognostic_section_fails():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Successful reperfusion | matters | |\n"  # no citation
    )
    failures = check_source_coverage(_schema(), md)
    assert any("prognostic" in f.lower() for f in failures)


def test_cited_prognostic_section_passes():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Successful reperfusion | matters | hermes (PMID 26898852) |\n"
    )
    assert check_source_coverage(_schema(), md) == []


def test_needs_synthesis_in_sourceable_area_fails():
    md = "## Prognostic Signs\n\nneeds synthesis\n"
    failures = check_source_coverage(_schema(), md)
    assert any("needs synthesis" in f.lower() for f in failures)


def test_patient_data_needs_input_is_exempt():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Reperfusion | matters | hermes (PMID 26898852) |\n\n"
        "## Imaging\nASPECTS: incomplete/needs input\n"
    )
    assert check_source_coverage(_schema(), md) == []


def test_non_thrombectomy_family_is_noop():
    assert check_source_coverage(_schema("spine_acdf"), "anything") == []


def test_needs_synthesis_outside_sourceable_section_is_ignored():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Reperfusion | matters | hermes (PMID 26898852) |\n\n"
        "## Imaging\nneeds synthesis here\n"
    )
    assert check_source_coverage(_schema(), md) == []


def test_uncited_four_column_row_is_caught():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Context | Strength | Source |\n|---|---|---|---|\n"
        "| Reperfusion | early | strong | |\n"  # empty final cell
    )
    failures = check_source_coverage(_schema(), md)
    assert any("uncited" in f.lower() for f in failures)


def test_rendered_thrombectomy_postop_passes_audit():
    schema = {
        "topic": "left MCA thrombectomy",
        "procedure_family": {"id": "endovascular_thrombectomy"},
        "case": {"postop_plan": {
            "destination": "Neuro-ICU", "neuro_checks": "q1h", "bp_goals": "x",
            "imaging_timing": "24h", "dvt_prophylaxis": "x",
            "medications": [], "drains_devices": [], "labs_monitoring": [],
            "discharge_criteria": [],
        }},
    }
    md = _render_postop(schema)
    assert check_source_coverage(schema, md) == []  # real render is fully cited
