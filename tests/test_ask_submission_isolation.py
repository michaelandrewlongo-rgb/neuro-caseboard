"""Hermetic unit tests for Ask submission isolation (app/ask_session.py), BACKLOG P1 #2.

Pure session-state logic — no Streamlit runtime, engine, corpus, or network. `app/` is a
bare-import script dir, so we put it on sys.path.
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ask_session import (is_new_submission, mark_answered, reset_conversation,
                         apply_pending_clear)


def test_answers_once_per_submission_not_every_rerun():
    state = {}
    assert is_new_submission(state, "blood supply of the lateral medulla") is True
    mark_answered(state, "blood supply of the lateral medulla")
    # A rerun (e.g. user toggles the PDF checkbox) with the SAME q must NOT re-answer.
    assert is_new_submission(state, "blood supply of the lateral medulla") is False


def test_a_new_distinct_question_is_a_new_submission():
    state = {}
    mark_answered(state, "Wallenberg syndrome findings")
    assert is_new_submission(state, "borders of the cavernous sinus") is True


def test_empty_query_is_never_a_submission():
    assert is_new_submission({}, "") is False
    assert is_new_submission({"ask_answered_q": "x"}, "") is False


def test_reset_conversation_clears_prior_question_and_evidence():
    state = {"ask_answered_q": "old q", "session_evidence": {"k1": {"answer: old q"}}}
    reset_conversation(state)
    assert "ask_answered_q" not in state
    assert state["session_evidence"] == {}
    # input clearing is deferred to top-of-script (cannot mutate a live widget key)
    assert state["_pending_clear_ask"] is True


def test_apply_pending_clear_resets_input_then_consumes_flag():
    state = {"_pending_clear_ask": True, "ask_q": "stale question"}
    apply_pending_clear(state)
    assert state["ask_q"] == ""
    assert "_pending_clear_ask" not in state  # one-shot
    # no-op when no pending clear
    state2 = {"ask_q": "kept"}
    apply_pending_clear(state2)
    assert state2["ask_q"] == "kept"


def test_after_reset_the_same_question_answers_again():
    state = {}
    mark_answered(state, "q1")
    reset_conversation(state)
    # New conversation: q1 is a fresh submission again.
    assert is_new_submission(state, "q1") is True
