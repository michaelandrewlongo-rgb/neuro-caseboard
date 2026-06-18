"""Tests for deterministic CasePrep intent fallback classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from caseprep.intent.heuristics import heuristic_intent_plan

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "intent_structurer_golden.json"


def _golden_examples() -> list[dict[str, str]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("example", _golden_examples())
def test_heuristic_intent_plan_matches_golden_examples(example: dict[str, str]):
    prompt = example["prompt"]
    intent_plan = heuristic_intent_plan(prompt)

    assert intent_plan.intent_type == example["intent_type"]
    assert intent_plan.subtype == example["subtype"]
    assert intent_plan.source == "heuristic_fallback"
    assert intent_plan.normalized_query == prompt.lower()
    assert intent_plan.template_sections
    assert intent_plan.retrieval_priorities


def test_heuristic_intent_plan_defaults_ambiguous_prompts_to_operative_briefing():
    intent_plan = heuristic_intent_plan("vestibular schwannoma")

    assert intent_plan.intent_type == "operative_briefing"
    assert intent_plan.subtype == "case_prep"
    assert "defaulted_to_operative_briefing" in intent_plan.warnings
