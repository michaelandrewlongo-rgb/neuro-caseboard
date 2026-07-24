"""Phase 4.1/4.3: the decision-furniture + calibrated-language rules are an A/B arm gated by
PROMPT_DECISION_FURNITURE, not a silent baseline change. FIX_PLAN §5 (4.1, 4.3)."""
from types import SimpleNamespace

import neuro_caseboard.woven_synth as ws


def _capture_system():
    captured = {}

    class Client:
        def generate(self, system, user, images, route=None):
            captured["system"] = system
            return "answer."

    ws.synthesize_woven("q", [], [], [], [], Client())  # empty hits -> build_citations([]) == []
    return captured["system"]


def test_decision_rules_absent_by_default(monkeypatch):
    monkeypatch.delenv("PROMPT_DECISION_FURNITURE", raising=False)
    assert "decision furniture" not in _capture_system()


def test_decision_rules_present_when_flag_on(monkeypatch):
    monkeypatch.setenv("PROMPT_DECISION_FURNITURE", "1")
    system = _capture_system()
    assert "decision furniture" in system and "Avoid absolute words" in system
