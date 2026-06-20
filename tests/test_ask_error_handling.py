"""Hermetic tests for Ask submission error handling (app/ask_errors.py), BACKLOG P3 #9.

Pure logic — no Streamlit/engine/network for the unit tests; the AppTest stubs the engine."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ask_errors import (classify_error, not_yet_failed, note_failure,  # noqa: E402
                        clear_failure)


def test_classify_error_gives_kind_specific_messages():
    assert classify_error(TimeoutError())[0] == "timeout"
    assert "timed out" in classify_error(TimeoutError())[1]
    assert classify_error(ConnectionError())[0] == "network"
    kind, msg = classify_error(ValueError("boom"))
    assert kind == "error" and "ValueError" in msg


def test_not_yet_failed_gates_on_per_question_marker():
    state = {}
    assert not_yet_failed(state, "q1") is True
    note_failure(state, "q1", "msg")
    assert not_yet_failed(state, "q1") is False      # same q awaits explicit retry
    assert not_yet_failed(state, "q2") is True        # a different q is unaffected


def test_note_and_clear_failure_roundtrip():
    state = {}
    note_failure(state, "q1", "actionable message")
    assert state["ask_failed_q"] == "q1" and state["ask_error"] == "actionable message"
    clear_failure(state)
    assert "ask_failed_q" not in state and "ask_error" not in state


def test_ask_lane_preserves_query_and_shows_error_on_failure(monkeypatch):
    """When the engine raises, the Ask lane shows an actionable error, preserves the query (does not
    clear ask_q), and does not mark the question answered. Hermetic: engine stubbed to raise."""
    import pytest
    pytest.importorskip("streamlit")
    import neuro_caseboard.qa as qa

    def _boom(question, **kw):
        raise TimeoutError("retrieval timed out")

    monkeypatch.setattr(qa, "answer_question", _boom)

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30)
    at.session_state["ask_q"] = "blood supply of the lateral medulla"
    at.run()
    assert len(at.exception) == 0                      # no uncaught crash
    errors = " ".join(e.value for e in at.error)
    assert "timed out" in errors                        # actionable error shown
    assert at.session_state["ask_q"] == "blood supply of the lateral medulla"  # query preserved
    answered = at.session_state["ask_answered_q"] if "ask_answered_q" in at.session_state else None
    assert answered != at.session_state["ask_q"]    # NOT marked answered -> Retry will re-run
