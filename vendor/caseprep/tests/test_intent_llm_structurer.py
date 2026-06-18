"""Tests for the LLM-backed intent structurer fallback boundary."""

from __future__ import annotations

import pytest

from caseprep.intent.llm_structurer import IntentLLMConfig, structure_intent


@pytest.mark.asyncio
async def test_structure_intent_uses_mocked_llm_when_enabled(monkeypatch):
    monkeypatch.setenv("CASEPREP_INTENT_STRUCTURER_ENABLED", "true")

    async def fake_call(query: str, config: IntentLLMConfig):
        assert query == "endo vs open MCA aneurysm outcomes"
        assert config.api_key == "test-key"
        return {
            "intent_type": "literature_review",
            "subtype": "comparative_outcomes",
            "confidence": 0.92,
            "normalized_query": "endo vs open mca aneurysm outcomes",
            "template_sections": ["clinical_question", "best_available_evidence"],
            "retrieval_priorities": ["outcomes", "systematic_reviews_meta_analyses"],
        }

    plan = await structure_intent(
        "endo vs open MCA aneurysm outcomes",
        config=IntentLLMConfig(api_key="test-key"),
        llm_call=fake_call,
    )

    assert plan.intent_type == "literature_review"
    assert plan.subtype == "comparative_outcomes"
    assert plan.source == "llm"
    assert plan.warnings == []


@pytest.mark.asyncio
async def test_structure_intent_falls_back_when_disabled(monkeypatch):
    monkeypatch.delenv("CASEPREP_INTENT_STRUCTURER_ENABLED", raising=False)

    async def fail_if_called(query: str, config: IntentLLMConfig):  # pragma: no cover
        raise AssertionError("LLM should not be called when disabled")

    plan = await structure_intent(
        "incidence of pseudoarthrosis after TLIF",
        config=IntentLLMConfig(api_key="test-key"),
        llm_call=fail_if_called,
    )

    assert plan.intent_type == "literature_review"
    assert plan.subtype == "incidence"
    assert plan.source == "heuristic_fallback"


@pytest.mark.asyncio
async def test_structure_intent_falls_back_on_validation_failure(monkeypatch):
    monkeypatch.setenv("CASEPREP_INTENT_STRUCTURER_ENABLED", "true")

    async def fake_bad_call(query: str, config: IntentLLMConfig):
        return {
            "intent_type": "technique_brief",
            "subtype": "technique",
            "confidence": 0.99,
        }

    plan = await structure_intent(
        "technique for ACDF",
        config=IntentLLMConfig(api_key="test-key"),
        llm_call=fake_bad_call,
    )

    assert plan.intent_type == "operative_briefing"
    assert plan.subtype == "technique"
    assert plan.source == "heuristic_fallback"
    assert "intent_llm_validation_failed" in plan.warnings


@pytest.mark.asyncio
async def test_structure_intent_falls_back_on_timeout(monkeypatch):
    monkeypatch.setenv("CASEPREP_INTENT_STRUCTURER_ENABLED", "true")

    async def timeout_call(query: str, config: IntentLLMConfig):
        raise TimeoutError("intent timeout")

    plan = await structure_intent(
        "endo vs open MCA aneurysm outcomes",
        config=IntentLLMConfig(api_key="test-key"),
        llm_call=timeout_call,
    )

    assert plan.intent_type == "literature_review"
    assert plan.subtype == "comparative_outcomes"
    assert plan.source == "heuristic_fallback"
    assert "intent_llm_call_failed" in plan.warnings


@pytest.mark.asyncio
async def test_structure_intent_falls_back_without_api_key(monkeypatch):
    monkeypatch.setenv("CASEPREP_INTENT_STRUCTURER_ENABLED", "true")

    async def fail_if_called(query: str, config: IntentLLMConfig):  # pragma: no cover
        raise AssertionError("LLM should not be called without api key")

    plan = await structure_intent(
        "retrosig for acoustic",
        config=IntentLLMConfig(api_key=""),
        llm_call=fail_if_called,
    )

    assert plan.intent_type == "operative_briefing"
    assert plan.subtype == "approach"
    assert "intent_llm_unavailable" in plan.warnings
