"""compile_dossier: AuditedManifest + evidence -> Dossier, fixing #2,#3,#5,#6,#7,#8,#9.

Parametrized across four subspecialties to prove no fix is topic-coupled.
"""

import dataclasses

import pytest

from neuro_caseboard.compile import compile_dossier, compile_case_dossier
from neuro_caseboard.model import Claim, EvidenceSummary
import tests.fixtures as fx


@pytest.fixture(params=fx.ALL_TOPICS)
def built(request):
    f = fx.build(request.param)
    d = compile_dossier(f.manifest, topic=f.topic, evidence=f.evidence,
                        card_evidence=f.card_evidence, page_texts=f.page_texts)
    return f, d


def test_title_includes_topic(built):
    f, d = built
    assert f.topic in d.title


def test_summary_is_single_evidence_axis_partition(built):
    f, d = built
    # one clean partition (supported + to_verify + quarantined == all cards),
    # no second axis to contradict it. needs_review(2) + no_evidence(1) -> to_verify 3.
    assert (d.summary.supported, d.summary.to_verify, d.summary.quarantined) == (3, 3, 1)
    total = d.summary.supported + d.summary.to_verify + d.summary.quarantined
    assert total == len(f.manifest.cards)


def test_canonical_sections_present(built):
    f, d = built
    headings = [s.heading for s in d.sections]
    assert headings[:3] == ["Anatomy at Risk", "Operative Plan", "Risk and Rescue"]


def test_claim_and_rationale_are_separate_fields(built):
    f, d = built
    claims = [c for s in d.sections for c in s.claims]
    assert claims
    for c in claims:
        assert c.why and c.why != c.text


def test_compound_bullet_becomes_checkbox_subitems(built):
    f, d = built
    compound = [c for s in d.sections for c in s.claims if c.sub_items]
    assert compound
    assert any(len(c.sub_items) >= 2 for c in compound)


def test_figure_linked_to_claim_with_complete_caption(built):
    f, d = built
    figs = [fig for s in d.sections for fig in s.figures]
    assert len(figs) == 1
    fig = figs[0]
    assert fig.fig_id == "F1"
    assert fig.claim_ref and fig.relevance
    truncated = f.evidence[0].metadata["caption"]
    assert fig.caption.endswith(".") and len(fig.caption) > len(truncated)
    linked = [c for s in d.sections for c in s.claims if fig.fig_id in c.figure_ids]
    assert len(linked) == 1


def test_cross_section_duplicate_collapsed_with_crossref(built):
    f, d = built
    by = {s.heading: s for s in d.sections}
    op_text = " ".join(c.text + " " + " ".join(c.sub_items)
                       for c in by["Operative Plan"].claims).lower()
    assert "closure" in op_text
    assert by["Risk and Rescue"].cross_refs
    risk_text = " ".join(c.text for c in by["Risk and Rescue"].claims)
    assert "Pre-brief" in risk_text  # distinct Risk claim survives dedup


def test_appendix_has_quarantined_claims_and_sources(built):
    f, d = built
    assert not d.appendix.is_empty()
    items = " ".join(i for e in d.appendix.entries for i in e.items).lower()
    sources = " ".join(s for e in d.appendix.entries for s in e.sources)
    assert any(k in items for k in ("lumbar", "endonasal", "radiosurgery", "thrombectomy"))
    assert f.evidence[0].metadata["citation"] in sources


def _case_card(tf, key, slot, q, status="no_evidence"):
    from caseprep.audit.card_auditor import AuditedCard
    return AuditedCard(question=q, why_it_matters="why " + key, target_file=tf,
                       section_key=key, compiler_slot=slot,
                       answerability="needs_patient_fact", audit_status=status)


def test_compile_case_dossier_renders_eight_sections_in_order():
    """The case path renders the eight §0 surfaces in order, on the single evidence axis,
    reusing the same compiler core as build (only the taxonomy differs)."""
    from caseprep.audit.card_auditor import AuditedManifest
    from neuro_caseboard.compile import compile_case_dossier
    from neuro_caseboard.case_context import CaseContext
    cards = [
        _case_card("01-clinical-summary.md", "presentation", "Presentation",
                   "62F with progressive cervical myelopathy"),
        _case_card("02-clinical-reasoning.md", "indication", "Indication",
                   "Operative decompression indicated for progressive cord signal change"),
        _case_card("04-operative-plan.md", "critical_steps", "Critical Steps",
                   "Decompress the canal then reconstruct the segment", status="supported"),
        _case_card("06-alternatives.md", "alternative_approach", "Alternative Approach",
                   "Posterior approach is the alternative if multilevel"),
        _case_card("05-risk-and-rescue.md", "catastrophic_complications",
                   "Catastrophic Complications", "Airway compromise from expanding hematoma"),
        _case_card("07-preop-optimization.md", "medical_optimization", "Medical Optimization",
                   "Optimize glycemic control before surgery"),
        _case_card("08-surgical-technique.md", "approach_corridor", "Approach Corridor",
                   "Develop the corridor along the avascular plane"),
        _case_card("09-case-figures.md", "schematic", "Schematic",
                   "Schematic of the operative corridor and target level"),
    ]
    manifest = AuditedManifest(procedure_family="case", cards=cards)
    case = CaseContext(level="C5-6", pathology="cervical spondylotic myelopathy",
                       procedure="ACDF", surgical_goal="decompression")
    d = compile_case_dossier(manifest, case=case)
    headings = [s.heading for s in d.sections]
    assert headings == [
        "Clinical Summary", "Clinical Reasoning", "Operative Plan", "Alternatives",
        "Risks", "Pre-op Optimization", "Surgical Technique", "Case Figures",
    ]
    assert "Case Dossier" in d.title and "C5-6" in d.title
    # single evidence axis preserved (1 supported, 7 no_evidence -> to_verify)
    assert (d.summary.supported, d.summary.quarantined) == (1, 0)
    assert d.summary.to_verify == 7


def test_model_has_no_confidence_axis(built):
    claim_fields = {fld.name for fld in dataclasses.fields(Claim)}
    assert "confidence" not in claim_fields and "confidence_band" not in claim_fields
    summ_fields = {fld.name for fld in dataclasses.fields(EvidenceSummary)}
    assert not any("conf" in n for n in summ_fields)
