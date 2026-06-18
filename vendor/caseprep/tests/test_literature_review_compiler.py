"""Tests for the literature review compiler artifact."""

from __future__ import annotations

from caseprep.compile.literature_review_compiler import compile_literature_review
from caseprep.core import EvidenceRecord, OutputIntentPlan
from caseprep.synthesis.section_synthesis import SectionDraft


def test_compile_literature_review_renders_evidence_grounded_sections():
    intent = OutputIntentPlan(
        intent_type="literature_review",
        subtype="comparative_outcomes",
        retrieval_priorities=["outcomes", "systematic_reviews_meta_analyses"],
    )
    evidence = [
        EvidenceRecord(
            id="pmid-1",
            source="pubmed",
            title="MCA aneurysm outcomes study",
            text="Compared endovascular and open treatment outcomes.",
            metadata={"year": "2024", "axis": "Outcomes / Comparative Evidence"},
        ),
        EvidenceRecord(
            id="corpus-1",
            source="corpus",
            title="Systematic review of MCA aneurysm therapy",
            text="Evidence synthesis abstract.",
            metadata={"year": "2022", "axis": "Systematic Reviews / Meta-analyses"},
        ),
    ]
    sections = [
        SectionDraft(
            id="outcomes-comparative-evidence",
            title="Outcomes / Comparative Evidence",
            body="- MCA aneurysm outcomes study: Compared endovascular and open treatment outcomes. [pmid-1]",
            evidence_ids=["pmid-1"],
            field_path="sections.outcomes-comparative-evidence",
        )
    ]

    markdown = compile_literature_review(
        topic="endo vs open MCA aneurysm outcomes",
        intent_plan=intent,
        evidence=evidence,
        sections=sections,
    )

    assert markdown.startswith("# Literature Review — endo vs open MCA aneurysm outcomes")
    assert "## Clinical question" in markdown
    assert "## Best available evidence" in markdown
    assert "[pmid-1]" in markdown
    assert "[corpus-1]" in markdown
    assert "No statement in this artifact is sourced from the intent-structuring LLM" in markdown


def test_compile_literature_review_marks_missing_evidence_as_insufficient():
    intent = OutputIntentPlan(intent_type="literature_review", subtype="incidence")

    markdown = compile_literature_review(
        topic="incidence of pseudoarthrosis after TLIF",
        intent_plan=intent,
        evidence=[],
        sections=[],
    )

    assert "Insufficient retrieved evidence" in markdown
    assert "## Bottom line with citations/provenance" in markdown
