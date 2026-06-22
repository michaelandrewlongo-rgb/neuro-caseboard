import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "summarize_grades.py"


@pytest.fixture(scope="module")
def summarize_module():
    spec = importlib.util.spec_from_file_location("summarize_grades", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_groundedness_summary_counts(summarize_module):
    rows = [{"verification": {"n_cited_claims": 4, "n_unsupported": 1}},
            {"verification": {"n_cited_claims": 2, "n_unsupported": 0}},
            {}]  # no verification -> skipped
    g = summarize_module.groundedness_summary(rows)
    assert g["answers_scored"] == 2
    assert g["answers_with_unsupported"] == 1
    assert g["total_cited_claims"] == 6
    assert g["total_unsupported"] == 1
    assert round(g["mean_groundedness"], 4) == round(((3 / 4) + (2 / 2)) / 2, 4)


def test_groundedness_summary_skips_zero_cited(summarize_module):
    g = summarize_module.groundedness_summary([{"verification": {"n_cited_claims": 0, "n_unsupported": 0}}])
    assert g["answers_scored"] == 0 and g["mean_groundedness"] == 1.0


def test_build_summary_includes_groundedness(summarize_module):
    grades = [{"question_id": "Q1", "domain": "Vascular", "score": 80, "letter_grade": "B"}]
    run_rows = [{"question_id": "Q1", "domain": "Vascular", "status": "completed",
                 "verification": {"n_cited_claims": 2, "n_unsupported": 1}}]
    summary = summarize_module.build_summary(grades, run_rows)
    assert "groundedness" in summary
    assert summary["groundedness"]["answers_scored"] == 1
    assert "groundedness" in summary["by_domain"]["Vascular"]
