"""Hermetic unit tests for Build evidence-grade refinement (neuro_caseboard/evidence_grade.py),
BACKLOG P2 #5. Pure classification — no corpus/LLM/network."""
from neuro_caseboard.evidence_grade import (GradeSignals, grade, summary_bucket,
                                            GRADES, GRADE_LABEL)


def test_grade_directly_vs_multi_source():
    assert grade(GradeSignals("supported", n_sources=1, cited=True)) == "directly-supported"
    assert grade(GradeSignals("supported", n_sources=3, cited=True)) == "multi-source"


def test_grade_standard_practice_for_needs_review():
    assert grade(GradeSignals("needs_review")) == "standard-practice"


def test_grade_unsupported_for_no_evidence_and_off_target():
    assert grade(GradeSignals("no_evidence")) == "unsupported"
    assert grade(GradeSignals("off_target")) == "unsupported"


def test_conflict_and_preference_take_precedence():
    assert grade(GradeSignals("supported", n_sources=3, has_conflict=True)) == "conflicting"
    assert grade(GradeSignals("supported", n_sources=3, is_preference=True)) == "attending-preference"
    # off_target still wins over conflict/preference (it is quarantined)
    assert grade(GradeSignals("off_target", has_conflict=True)) == "unsupported"


def test_summary_bucket_preserves_three_way_invariant():
    assert summary_bucket("directly-supported") == "supported"
    assert summary_bucket("multi-source") == "supported"
    for c in ("standard-practice", "attending-preference", "conflicting", "unsupported"):
        assert summary_bucket(c) == "to_verify"


def test_grades_and_labels_consistent():
    assert set(GRADES) == set(GRADE_LABEL)
    assert len(GRADES) == 6
