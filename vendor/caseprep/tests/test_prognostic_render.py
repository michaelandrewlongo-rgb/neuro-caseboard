from caseprep.schema import _render_postop


def _thrombectomy_schema() -> dict:
    return {
        "topic": "left MCA thrombectomy",
        "procedure_family": {"id": "endovascular_thrombectomy"},
        "case": {
            "postop_plan": {
                "destination": "Neuro-ICU", "neuro_checks": "q1h",
                "bp_goals": "per attending", "imaging_timing": "24h CT",
                "dvt_prophylaxis": "per protocol",
                "medications": [], "drains_devices": [],
                "labs_monitoring": [], "discharge_criteria": [],
            },
        },
    }


def test_thrombectomy_postop_has_prognostic_section():
    out = _render_postop(_thrombectomy_schema())
    assert "## Prognostic Signs" in out
    assert "Favorable" in out and "Unfavorable" in out
    assert "Successful reperfusion (mTICI 2b-3)" in out
    assert "Low ASPECTS" in out
    assert "26898852" in out  # HERMES PMID rendered as a source ref
    assert "Immediate Postop Orders" in out  # existing postop content still renders


def test_non_thrombectomy_postop_has_no_prognostic_section():
    schema = {
        "topic": "ACDF",
        "procedure_family": {"id": "spine_acdf"},
        "case": {"postop_plan": {
            "destination": "floor", "neuro_checks": "q4h", "bp_goals": "normal",
            "imaging_timing": "as needed", "dvt_prophylaxis": "SCDs",
            "medications": [], "drains_devices": [], "labs_monitoring": [],
            "discharge_criteria": [],
        }},
    }
    out = _render_postop(schema)
    assert "Prognostic Signs" not in out
