"""Ask style variant: style="extract" -> cited bullet points, sources only.

The contract under test is deliberately narrow: the extract style must change ONLY the
synthesis system prompt (and its telemetry route). Retrieval, citation building, and the
verification gate must behave exactly as they do for the default prose answer, and the
default must stay byte-identical to what it was before the style existed.
"""

from dataclasses import dataclass, field

from neuro_caseboard import qa, qa_stream
from neuro_caseboard.woven_synth import (
    WOVEN_CORPUS_RULE, WOVEN_EXTRACT_RULES, WOVEN_SYSTEM, build_woven_system,
    synthesize_woven)


class RecordingSynth:
    """Captures the exact (system, user, route) the orchestrator sends."""

    def __init__(self, answer="- fact one [1]\n- fact two [2]\n"):
        self.answer = answer
        self.calls = []

    def generate(self, system, user, images, route=None):
        self.calls.append({"system": system, "user": user, "route": route})
        return self.answer

    def generate_stream(self, system, user, images, route=None):
        self.calls.append({"system": system, "user": user, "route": route})
        yield self.answer


def Hit(n=1):
    """The real retrieval Hit — same fake the existing woven tests use."""
    from neuro_core.index import Hit as _Hit
    return _Hit(id=str(n), book="Greenberg", chapter="Ch", page=n, text=f"passage {n}")


# --- the prompt itself ------------------------------------------------------------------

def test_default_system_prompt_is_unchanged_by_the_feature():
    # Regression guard: adding a style must not perturb the default answer's prompt.
    assert build_woven_system(corpus_records=None, style=None) == WOVEN_SYSTEM
    assert build_woven_system(corpus_records=None, style="") == WOVEN_SYSTEM
    assert WOVEN_EXTRACT_RULES not in build_woven_system(None, None)


def test_extract_style_appends_rules_and_keeps_the_base_contract():
    system = build_woven_system(corpus_records=None, style="extract")
    assert system.startswith(WOVEN_SYSTEM)          # base rules (citations, refusal) survive
    assert system.endswith(WOVEN_EXTRACT_RULES)
    lowered = WOVEN_EXTRACT_RULES.lower()
    assert "bullet" in lowered                       # the format ask
    assert "citation marker" in lowered              # every bullet stays attributable
    assert "do not add background knowledge" in lowered   # sources-only, no free synthesis


def test_extract_style_composes_with_the_corpus_rule():
    system = build_woven_system(corpus_records=[object()], style="extract")
    assert WOVEN_CORPUS_RULE in system and WOVEN_EXTRACT_RULES in system


def test_decision_furniture_arm_still_applies_under_extract(monkeypatch):
    from neuro_caseboard.woven_synth import WOVEN_DECISION_RULES
    monkeypatch.setenv("PROMPT_DECISION_FURNITURE", "1")
    system = build_woven_system(corpus_records=None, style="extract")
    assert WOVEN_DECISION_RULES in system and WOVEN_EXTRACT_RULES in system


# --- synthesize_woven plumbing ------------------------------------------------------------

def test_synthesize_woven_sends_extract_rules_and_its_own_route():
    synth = RecordingSynth()
    out = synthesize_woven("q", [Hit()], [], [], [], synth, style="extract")
    call = synth.calls[0]
    assert WOVEN_EXTRACT_RULES in call["system"]
    assert call["route"] == "ask.synth.extract"      # separable in the telemetry DB
    assert out.answer == synth.answer


def test_synthesize_woven_default_is_untouched():
    synth = RecordingSynth()
    synthesize_woven("q", [Hit()], [], [], [], synth)
    call = synth.calls[0]
    assert call["system"] == WOVEN_SYSTEM
    assert call["route"] == "ask.synth"


def test_user_prompt_is_identical_across_styles():
    # The style is an instruction change only — the evidence block handed to the model
    # (passages/figures/studies) must not differ, or the arms aren't comparable.
    plain, extract = RecordingSynth(), RecordingSynth()
    synthesize_woven("q", [Hit()], [], [], [], plain)
    synthesize_woven("q", [Hit()], [], [], [], extract, style="extract")
    assert plain.calls[0]["user"] == extract.calls[0]["user"]


# --- orchestrators honor the style ---------------------------------------------------------

@dataclass
class _Plan:
    question: str = "q"
    hits: list = field(default_factory=lambda: [Hit()])
    figures: list = field(default_factory=list)
    images: list = field(default_factory=list)
    variant: object = None


def test_blocking_woven_path_threads_style_through(monkeypatch):
    synth = RecordingSynth()
    res = qa._answer_question_woven(
        "q", synth_client=synth, plan_a=lambda: _Plan(), retrieve_b=lambda: [],
        retrieve_c=lambda: [], style="extract")
    assert WOVEN_EXTRACT_RULES in synth.calls[0]["system"]
    assert res.answer == synth.answer
    assert res.citations                              # citation building still ran


def test_streaming_path_threads_style_through():
    synth = RecordingSynth()
    events = []
    qa_stream.stream_answer("q", events.append, synth_client=synth, plan_a=lambda: _Plan(),
                            retrieve_b=lambda: [], retrieve_c=lambda: [], style="extract")
    assert WOVEN_EXTRACT_RULES in synth.calls[0]["system"]
    assert synth.calls[0]["route"] == "ask.stream.extract"
    answer = next(e for e in events if e.get("type") == "answer")
    assert answer["answer"] == synth.answer
    assert answer["citations"]                        # sources still emitted


def test_streaming_default_prompt_unchanged():
    synth = RecordingSynth()
    qa_stream.stream_answer("q", lambda e: None, synth_client=synth, plan_a=lambda: _Plan(),
                            retrieve_b=lambda: [], retrieve_c=lambda: [])
    assert synth.calls[0]["system"] == WOVEN_SYSTEM
    assert synth.calls[0]["route"] == "ask.stream"


def test_non_woven_path_warns_that_style_is_dropped(caplog):
    """Silent-failure guard: separate-lane mode can't apply a style — it must say so."""
    class _QR:
        answer = "prose"
        citations = []
        figures = []
    with caplog.at_level("WARNING"):
        qa.answer_question("q", lane_a=lambda: _QR(), lane_b=lambda: None, style="extract")
    assert any("style" in r.getMessage() and "ignored" in r.getMessage()
               for r in caplog.records)


# --- API surface ---------------------------------------------------------------------------

def test_api_rejects_unknown_style():
    from fastapi.testclient import TestClient
    import api.server as server
    client = TestClient(server.app)
    for path in ("/api/ask", "/api/ask/start"):
        r = client.post(path, json={"question": "q", "style": "haiku"})
        assert r.status_code == 422, path
        assert "unknown style" in r.json()["error"]


def test_api_passes_style_to_the_engine(monkeypatch):
    from fastapi.testclient import TestClient
    import api.server as server
    seen = {}

    def fake_answer(question, **kw):
        seen.update(kw)
        class R:
            answer = "- fact [1]"
            citations = []
            figures = []
            literature = None
            verification = None
            corpus = []
            evidence_spans = []
            decision_card = None
        return R()

    monkeypatch.setattr("neuro_caseboard.qa.answer_question", fake_answer)
    client = TestClient(server.app)
    r = client.post("/api/ask", json={"question": "q", "style": "extract"})
    assert r.status_code == 200
    assert seen.get("style") == "extract"


def test_api_default_style_is_none_not_a_string(monkeypatch):
    from fastapi.testclient import TestClient
    import api.server as server
    seen = {}

    def fake_answer(question, **kw):
        seen.update(kw)
        class R:
            answer = "prose"
            citations = []
            figures = []
            literature = None
            verification = None
            corpus = []
            evidence_spans = []
            decision_card = None
        return R()

    monkeypatch.setattr("neuro_caseboard.qa.answer_question", fake_answer)
    client = TestClient(server.app)
    client.post("/api/ask", json={"question": "q"})
    assert seen.get("style") is None      # falsy "" must not read as a requested style
