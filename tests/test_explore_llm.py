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
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert llm_available() is False


def test_llm_available_with_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert llm_available() is True


# --- refinement (two-pass) -------------------------------------------------

def _two_pass(draft_payload, refine_payload):
    """complete_fn that returns the draft on the 1st call, refinement on the 2nd."""
    calls = {"n": 0}

    def fn(system, user):
        calls["n"] += 1
        return draft_payload if calls["n"] == 1 else refine_payload
    return fn


_REFINE_EXTRA = {
    "cards": [
        # genuinely new, same slot as an existing risk card -> must be ADDED
        _card("05-risk-and-rescue.md", "catastrophic_complications",
              "Adenosine-induced flow arrest for premature aneurysm rupture"),
        # near-duplicate of an existing draft card -> must be DROPPED
        _card("05-risk-and-rescue.md", "rescue_triggers",
              "Plan for intraoperative seizure: cold saline irrigation"),
    ]
}


def test_refine_pass_adds_distinct_cards_and_dedups(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_REFINE", "1")
    fn = _two_pass(json.dumps(VALID_CARDS), json.dumps(_REFINE_EXTRA))
    m = build_llm_manifest("ruptured MCA aneurysm clipping", complete_fn=fn)
    qs = [c.question for c in m.cards]
    assert any("Adenosine-induced flow arrest" in q for q in qs)      # distinct -> added
    assert sum("cold saline irrigation" in q for q in qs) == 1        # near-dup -> not duplicated
    assert len(m.cards) == 7                                          # 6 draft + 1 new


def test_refine_disabled_by_env(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_REFINE", "0")
    fn = _two_pass(json.dumps(VALID_CARDS), json.dumps(_REFINE_EXTRA))
    m = build_llm_manifest("anything", complete_fn=fn)
    assert len(m.cards) == 6                                          # draft only


def test_refine_failure_keeps_draft(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_REFINE", "1")
    calls = {"n": 0}

    def fn(system, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(VALID_CARDS)
        raise RuntimeError("refine api down")

    m = build_llm_manifest("anything", complete_fn=fn)
    assert m is not None and len(m.cards) == 6                        # draft survives
