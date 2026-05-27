"""Schema validation tests for LLM intent-structurer payloads."""

from __future__ import annotations

import pytest

from caseprep.core import CasePrepValidationError
from caseprep.intent.schema import validate_intent_payload


def test_validate_intent_payload_accepts_narrow_schema():
    plan = validate_intent_payload(
        {
            "intent_type": "literature_review",
            "subtype": "comparative_outcomes",
            "confidence": 0.91,
            "normalized_query": "endo vs open mca aneurysm outcomes",
            "entities": {"comparison_arms": ["endo", "open"]},
            "template_sections": ["clinical_question", "best_available_evidence"],
            "retrieval_priorities": ["outcomes", "systematic_reviews_meta_analyses"],
            "clarification_needed": False,
            "warnings": [],
        },
        source="llm",
    )

    assert plan.intent_type == "literature_review"
    assert plan.subtype == "comparative_outcomes"
    assert plan.source == "llm"
    assert plan.template_sections == ["clinical_question", "best_available_evidence"]


@pytest.mark.parametrize(
    "payload",
    [
        {"intent_type": "technique_brief", "subtype": "technique", "confidence": 0.8},
        {"intent_type": "operative_briefing", "subtype": "technique", "confidence": 1.5},
        {"intent_type": "operative_briefing", "subtype": "technique", "template_sections": "steps"},
    ],
)
def test_validate_intent_payload_rejects_invalid_schema(payload):
    with pytest.raises(CasePrepValidationError):
        validate_intent_payload(payload)


@pytest.mark.parametrize(
    "bad_section",
    [
        "Endovascular treatment is superior",
        "Therefore choose clipping",
        "Outcome rate is 42%",
        "This is better because morbidity is lower.",
    ],
)
def test_validate_intent_payload_rejects_answer_language_in_template_labels(bad_section: str):
    with pytest.raises(CasePrepValidationError):
        validate_intent_payload(
            {
                "intent_type": "literature_review",
                "subtype": "comparative_outcomes",
                "confidence": 0.8,
                "template_sections": [bad_section],
                "retrieval_priorities": ["outcomes"],
            },
        )
