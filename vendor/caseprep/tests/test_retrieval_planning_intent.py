"""Intent-aware retrieval planning tests."""

from __future__ import annotations

import pytest

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.core import BuildCasePlanRequest, EvidenceRecord, OutputIntentPlan
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan
from caseprep.retrieval_planning import build_case_queries


def test_literature_review_intent_uses_evidence_oriented_axes():
    case = parse_case_input("endo vs open MCA aneurysm outcomes")
    intent = OutputIntentPlan(
        intent_type="literature_review",
        subtype="comparative_outcomes",
        entities={"comparison_arms": ["endo", "open"]},
    )

    axes = build_case_queries(case, select_procedure_family(case), intent_plan=intent)

    assert [axis.id for axis in axes] == [
        "clinical_question",
        "outcomes",
        "rates",
        "risk_factors",
        "reviews",
    ]
    assert axes[0].label == "Clinical Question Framing"
    assert "outcomes" in axes[1].query.lower()
    assert "incidence" in axes[2].query.lower()
    assert "risk factors" in axes[3].query.lower()
    assert axes[-1].filter_type == "systematic_review"
    assert "Anatomy / Relevant Structures" not in [axis.label for axis in axes]


def test_operative_briefing_intent_preserves_operative_axes():
    case = parse_case_input("technique for ACDF")
    intent = OutputIntentPlan(intent_type="operative_briefing", subtype="technique")

    axes = build_case_queries(case, select_procedure_family(case), intent_plan=intent)

    assert [axis.label for axis in axes] == [
        "Anatomy / Relevant Structures",
        "Outcomes / Evidence",
        "Surgical Technique",
        "Complications",
        "Reviews / Landmarks",
    ]


@pytest.mark.asyncio
async def test_core_builder_exposes_intent_and_uses_literature_axes():
    pubmed_calls = []

    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            pubmed_calls.append((query, filter_type))
            return [EvidenceRecord(id=f"pmid-{len(pubmed_calls)}", source="pubmed", title=query)]

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    intent = OutputIntentPlan(
        intent_type="literature_review",
        subtype="incidence",
        retrieval_priorities=["incidence_rates", "systematic_reviews_meta_analyses"],
        source="explicit",
    )

    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="incidence of pseudoarthrosis after TLIF",
            max_per_category=1,
            intent_plan=intent,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    assert result.intent_plan == intent
    assert result.structured["intent_plan"]["intent_type"] == "literature_review"
    assert result.structured["intent_plan"]["subtype"] == "incidence"
    assert result.structured["retrieval"]["pubmed_queries"][0]["id"] == "clinical_question"
    assert result.structured["retrieval"]["pubmed_queries"][2]["id"] == "rates"
    assert "incidence" in pubmed_calls[2][0].lower()
