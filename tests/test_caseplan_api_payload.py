"""Tests for selecting primary artifacts in /api/build payloads."""

from __future__ import annotations

from caseprep.adapters.caseplan import caseplan_api_payload
from caseprep.core import ArtifactRef, BuildCasePlanResult, OutputIntentPlan


def test_caseplan_api_payload_uses_literature_review_primary_artifact(tmp_path):
    artifact_path = tmp_path / "literature_review.md"
    artifact_path.write_text("# Literature Review\n\nPrimary artifact body", encoding="utf-8")
    intent = OutputIntentPlan(intent_type="literature_review", subtype="incidence")
    result = BuildCasePlanResult(
        topic="incidence of pseudoarthrosis after TLIF",
        markdown="# Core Summary\n\nFallback only",
        output_dir=tmp_path,
        artifacts=[
            ArtifactRef(
                path=artifact_path,
                kind="markdown",
                media_type="text/markdown",
                label="literature_review.md",
            )
        ],
        intent_plan=intent,
    )

    payload = caseplan_api_payload(
        result,
        slug="incidence-of-pseudoarthrosis-after-tlif",
        output_dir=str(tmp_path),
        caseplan_id=123,
    )

    assert payload["summary"] == "# Literature Review\n\nPrimary artifact body"
    assert payload["intent"] == intent.to_dict()
    assert payload["primary_artifact"]["label"] == "literature_review.md"
    assert payload["artifacts"][0]["label"] == "literature_review.md"


def test_caseplan_api_payload_falls_back_to_core_summary_when_artifact_missing(tmp_path):
    result = BuildCasePlanResult(
        topic="retrosig for acoustic",
        markdown="# Core Summary",
        output_dir=tmp_path,
        intent_plan=OutputIntentPlan(intent_type="operative_briefing", subtype="approach"),
    )

    payload = caseplan_api_payload(
        result,
        slug="retrosig-for-acoustic",
        output_dir=str(tmp_path),
        caseplan_id=124,
    )

    assert payload["summary"] == "# Core Summary"
    assert payload["primary_artifact"] is None
