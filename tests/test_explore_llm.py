"""LLM-backed Explorer: parse/validate/build QuestionCards from a model's JSON.

The model call is dependency-injected (complete_fn), so these tests are deterministic
and never touch the network.
"""

import json

import pytest

from neuro_caseboard.explore_llm import build_llm_manifest, llm_available


def _fake(payload):
    """Return a complete_fn that ignores its args and returns the given JSON string."""
    return lambda system, user: payload


def _card(target, key, q="a specific operative question", w="a specific consequence"):
    return {"target_file": target, "section_key": key, "question": q, "why_it_matters": w}


VALID_CARDS = {
    "cards": [
        _card("03-anatomy-at-risk.md", "neural_structures",
              "Confirm corticospinal tract location relative to the cavity"),
        _card("03-anatomy-at-risk.md", "no_fly_zones"),
        _card("04-operative-plan.md", "critical_steps",
              "Internal debulking before capsule dissection"),
        _card("04-operative-plan.md", "monitoring"),
        _card("05-risk-and-rescue.md", "rescue_triggers",
              "Plan for intraoperative seizure: cold saline irrigation"),
        _card("05-risk-and-rescue.md", "mitigation"),
        # invalid section_key -> dropped
        _card("03-anatomy-at-risk.md", "made_up_key"),
        # section_key not in this target_file's group -> dropped
        _card("05-risk-and-rescue.md", "neural_structures"),
        # empty question -> dropped
        _card("04-operative-plan.md", "positioning", q="  "),
    ]
}


def test_builds_manifest_keeping_only_valid_cards():
    m = build_llm_manifest("awake left frontal glioma", complete_fn=_fake(json.dumps(VALID_CARDS)))
    assert m is not None
    assert len(m.cards) == 6   # 6 valid, 3 invalid dropped
    keys = {c.section_key for c in m.cards}
    assert {"neural_structures", "critical_steps", "rescue_triggers"} <= keys
    assert "made_up_key" not in keys


def test_derives_compiler_slot_from_section_key():
    m = build_llm_manifest("posterior fossa tumor", complete_fn=_fake(json.dumps(VALID_CARDS)))
    slots = {c.section_key: c.compiler_slot for c in m.cards}
    assert slots["neural_structures"] == "Neural Structures"
    assert slots["critical_steps"] == "Critical Steps"
    assert slots["rescue_triggers"] == "Rescue Triggers"


def test_cards_target_the_three_canonical_files():
    m = build_llm_manifest("carotid endarterectomy", complete_fn=_fake(json.dumps(VALID_CARDS)))
    files = {c.target_file for c in m.cards}
    assert files <= {"03-anatomy-at-risk.md", "04-operative-plan.md", "05-risk-and-rescue.md"}


def test_returns_none_on_completion_error():
    def boom(system, user):
        raise RuntimeError("api down")
    assert build_llm_manifest("anything", complete_fn=boom) is None


def test_returns_none_on_unparseable_output():
    assert build_llm_manifest("anything", complete_fn=_fake("not json at all")) is None


def test_returns_none_when_too_few_valid_cards():
    thin = {"cards": [{"target_file": "03-anatomy-at-risk.md", "section_key": "variants",
                       "question": "q", "why_it_matters": "w"}]}
    assert build_llm_manifest("anything", complete_fn=_fake(json.dumps(thin))) is None


def test_llm_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert llm_available() is False
