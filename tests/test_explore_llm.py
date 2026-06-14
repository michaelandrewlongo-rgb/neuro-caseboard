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
    monkeypatch.delenv("CASEBOARD_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert llm_available() is True


# --- Vertex AI provider (GCP free credits, quality-first) ------------------

from neuro_caseboard.explore_llm import _llm_provider, _model_for
import neuro_caseboard.explore_llm as _el


def test_explicit_provider_vertex_overrides_other_keys(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_PROVIDER", "vertex")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")   # present but must be ignored
    assert _llm_provider() == "vertex"


def test_provider_defaults_to_openrouter_then_anthropic(monkeypatch):
    monkeypatch.delenv("CASEBOARD_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert _llm_provider() == "openrouter"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert _llm_provider() == "anthropic"


def test_vertex_uses_gemini_pro_for_every_role(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_PROVIDER", "vertex")
    for v in ("CASEBOARD_LLM_MODEL", "CASEBOARD_AUTHOR_MODEL",
              "CASEBOARD_PLANNER_MODEL", "CASEBOARD_CRITIC_MODEL"):
        monkeypatch.delenv(v, raising=False)
    # quality, not value: the strong model on every role (no cheap author tier)
    assert _model_for("author") == "gemini-2.5-pro"
    assert _model_for("planner") == "gemini-2.5-pro"
    assert _model_for("critic") == "gemini-2.5-pro"


def test_vertex_model_env_override(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_PROVIDER", "vertex")
    monkeypatch.setenv("CASEBOARD_LLM_MODEL", "gemini-2.5-flash")
    assert _model_for("author") == "gemini-2.5-flash"


def test_llm_available_with_vertex(monkeypatch):
    # `llm_available()` for the vertex provider returns True iff GOOGLE_CLOUD_PROJECT is set
    # AND `google.genai` is importable. Inject a stand-in module so this asserts the LOGIC
    # deterministically — whether or not the optional `google-genai` SDK (the `[vertex]`
    # extra) is installed — matching this file's "never touch the network" contract.
    import sys
    import types

    google_mod = sys.modules.get("google") or types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setattr(google_mod, "genai", genai_mod, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setenv("CASEBOARD_LLM_PROVIDER", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-x")
    assert llm_available() is True


def test_llm_unavailable_with_vertex_when_sdk_missing(monkeypatch):
    # The other branch, also pinned independently of the environment: with the provider and
    # project set but the SDK unimportable, the Explorer must report unavailable (and fall
    # back to the deterministic path). Setting the sys.modules entry to None forces the
    # `import google.genai` inside llm_available() to raise, regardless of what is installed.
    import sys

    monkeypatch.setitem(sys.modules, "google.genai", None)
    monkeypatch.setenv("CASEBOARD_LLM_PROVIDER", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-x")
    assert llm_available() is False


def test_default_complete_routes_to_vertex(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_PROVIDER", "vertex")
    seen = {}

    def fake_vertex(s, u, **k):
        seen["args"] = (s, u, k)
        return '{"cards": []}'

    monkeypatch.setattr(_el, "_vertex_complete", fake_vertex)
    out = _el._default_complete("SYS", "USR", model="m", temperature=0.2)
    assert out == '{"cards": []}'
    assert seen["args"][0] == "SYS" and seen["args"][1] == "USR"


# --- planner -> author -> critic -------------------------------------------

from neuro_caseboard.explore_llm import plan_coverage


def _roles(*, themes=None, draft=None, critic=None):
    """Role-specific fakes returning canned JSON for planner / author / critic."""
    return (
        (lambda s, u: json.dumps(themes)) if themes is not None else None,
        (lambda s, u: json.dumps(draft)) if draft is not None else None,
        (lambda s, u: json.dumps(critic)) if critic is not None else None,
    )


def test_planner_unions_ontology_floor_and_samples():
    plan_fn = lambda s, u: json.dumps({"themes": ["Sphenoid ridge drilling for a flat approach"]})
    themes = plan_coverage("pterional clipping of a ruptured left MCA aneurysm", plan_fn)
    joined = " | ".join(themes).lower()
    assert "proximal control" in joined                          # ontology aneurysm dimension
    assert "adenosine" in joined                                 # ontology aneurysm rescue
    assert any("sphenoid ridge" in t.lower() for t in themes)    # planner-contributed theme


def test_planner_floor_survives_planner_failure():
    def boom(s, u):
        raise RuntimeError("planner down")
    themes = plan_coverage(
        "suboccipital resection of pediatric fourth-ventricle medulloblastoma", boom)
    joined = " | ".join(themes).lower()
    assert "hydrocephalus" in joined and "csf cytology" in joined  # ontology floor still present


_CRITIC_ADD = {
    "add": [
        # genuinely new -> added even though same risk slot as a draft card
        _card("05-risk-and-rescue.md", "catastrophic_complications",
              "Adenosine-induced flow arrest for a premature aneurysm-neck rupture"),
        # near-duplicate of a draft card -> dropped
        _card("05-risk-and-rescue.md", "rescue_triggers",
              "Plan for intraoperative seizure: cold saline irrigation"),
    ],
    "fix": [],
}


def test_critic_adds_distinct_and_dedups():
    plan_fn, author_fn, critic_fn = _roles(
        themes={"themes": ["proximal control"]}, draft=VALID_CARDS, critic=_CRITIC_ADD)
    m = build_llm_manifest("ruptured MCA aneurysm clipping",
                           plan_fn=plan_fn, author_fn=author_fn, critic_fn=critic_fn)
    qs = [c.question for c in m.cards]
    assert any("Adenosine-induced flow arrest" in q for q in qs)   # distinct -> added
    assert sum("cold saline irrigation" in q for q in qs) == 1     # near-dup -> not duplicated
    assert len(m.cards) == 7                                        # 6 draft + 1 new


def test_critic_reanchors_fabrication_instead_of_deleting():
    fix = {"add": [], "fix": [{
        "match": "corticospinal tract location",
        "question": ("Corticospinal tract runs in the posterior limb of the internal "
                     "capsule; confirm its position relative to the cavity"),
        "why_it_matters": "A wrong tract location risks motor injury"}]}
    plan_fn, author_fn, critic_fn = _roles(themes={"themes": []}, draft=VALID_CARDS, critic=fix)
    m = build_llm_manifest("awake left frontal glioma",
                           plan_fn=plan_fn, author_fn=author_fn, critic_fn=critic_fn)
    qs = [c.question for c in m.cards]
    assert any("posterior limb of the internal capsule" in q for q in qs)  # re-anchored
    assert len(m.cards) == 6                                                # repaired, not added/deleted


def test_critic_disabled_by_env(monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM_CRITIC", "0")
    plan_fn, author_fn, critic_fn = _roles(
        themes={"themes": []}, draft=VALID_CARDS, critic=_CRITIC_ADD)
    m = build_llm_manifest("anything", plan_fn=plan_fn, author_fn=author_fn, critic_fn=critic_fn)
    assert len(m.cards) == 6                                        # critic skipped


def test_critic_failure_keeps_draft():
    def boom(s, u):
        raise RuntimeError("critic down")
    plan_fn, author_fn, _ = _roles(themes={"themes": []}, draft=VALID_CARDS)
    m = build_llm_manifest("anything", plan_fn=plan_fn, author_fn=author_fn, critic_fn=boom)
    assert m is not None and len(m.cards) == 6                      # draft survives
