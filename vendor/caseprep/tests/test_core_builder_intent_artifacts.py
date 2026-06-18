"""Core builder tests for intent-selected primary artifacts."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanRequest, EvidenceRecord, OutputIntentPlan
from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan


class EmptyRadiologyRetriever:
    async def retrieve(self, query, *, max_results=5, modality=None):
        return []


class EmptyCorpusRetriever:
    def retrieve(self, fts_query, *, subdomain=None, top_n=8):
        return []


@pytest.mark.asyncio
async def test_core_builder_writes_literature_review_artifact_for_lit_intent(tmp_path):
    class FakePubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            return [
                EvidenceRecord(
                    id=f"pmid-{filter_type or 'question'}",
                    source="pubmed",
                    title=f"Evidence for {query}",
                    text="Retrieved abstract sentence.",
                    metadata={"axis": "Outcomes / Comparative Evidence"},
                )
            ]

    intent = OutputIntentPlan(intent_type="literature_review", subtype="incidence")
    result = await build_core_case_plan(
        BuildCasePlanRequest(
            case_input="incidence of pseudoarthrosis after TLIF",
            max_per_category=1,
            output_dir=tmp_path / "lit-review-caseprep",
            intent_plan=intent,
        ),
        retrievers=CoreRetrieverSet(
            pubmed=FakePubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
    )

    literature_path = tmp_path / "lit-review-caseprep" / "literature_review.md"
    assert literature_path.exists()
    markdown = literature_path.read_text(encoding="utf-8")
    assert markdown.startswith("# Literature Review — incidence of pseudoarthrosis after TLIF")
    assert "No statement in this artifact is sourced from the intent-structuring LLM" in markdown
    assert any(artifact.label == "literature_review.md" for artifact in result.artifacts)
    lit_artifact = next(artifact for artifact in result.artifacts if artifact.label == "literature_review.md")
    assert lit_artifact.metadata["primary"] is True
    assert result.intent_plan == intent
