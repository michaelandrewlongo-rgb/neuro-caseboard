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


def test_compile_attaches_fine_grade_and_preserves_summary():
    """compile_dossier attaches a fine grade per claim without changing the 3-way EvidenceSummary.
    Hermetic: in-memory AuditedCards, no corpus/LLM/network."""
    from caseprep.audit.card_auditor import AuditedCard, AuditedManifest
    from neuro_caseboard.compile import compile_dossier
    from neuro_caseboard.pipeline import _sources_from_audited

    TOPIC = "pterional craniotomy for MCA aneurysm clipping"
    on = {"id": "p_on", "title": "Lawton - Seven Aneurysms", "source": "corpus",
          "text_snippet": "pterional approach to the MCA bifurcation aneurysm"}
    cards = [
        AuditedCard(question="Which arteries are at risk during the pterional approach?",
                    why_it_matters="Defines the dissection corridor.",
                    target_file="anatomy", section_key="arteries_at_risk", compiler_slot="",
                    answerability="answerable", audit_status="supported", papers=[dict(on)]),
        AuditedCard(question="Are prophylactic antibiotics given routinely?",
                    why_it_matters="Standard prep step.",
                    target_file="prep", section_key="antibiotics", compiler_slot="",
                    answerability="answerable", audit_status="needs_review", papers=[]),
    ]
    m = AuditedManifest(procedure_family=TOPIC, cards=cards)
    dossier = compile_dossier(m, topic=TOPIC, evidence=_sources_from_audited(m))

    grades = {cl.grade for s in dossier.sections for cl in s.claims}
    assert grades & {"directly-supported", "multi-source"}   # the supported card
    assert "standard-practice" in grades                      # the needs_review card
    assert all(cl.grade for s in dossier.sections for cl in s.claims)  # every claim graded
    # 3-way summary invariant: exactly one corpus-supported card, unchanged by the fine grade
    assert dossier.summary.supported == 1
