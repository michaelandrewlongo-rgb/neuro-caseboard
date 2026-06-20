"""Pure session-state helpers that isolate each Ask submission (BACKLOG P1 #2).

Kept out of the Streamlit script so the isolation logic is unit-testable on a plain dict.
The app passes ``st.session_state``; tests pass a dict. No Streamlit/engine/network here.
"""
from __future__ import annotations

from typing import MutableMapping


def is_new_submission(state: MutableMapping, q: str) -> bool:
    """True iff ``q`` is a non-empty question we have not already answered this conversation.

    Gating on this (instead of "answer whenever the box is non-empty") makes a rerun caused by
    any other widget — the PDF checkbox, the Build button — NOT re-run the engine on a stale q.
    """
    return bool(q) and q != state.get("ask_answered_q")


def mark_answered(state: MutableMapping, q: str) -> None:
    """Record that ``q`` has been answered so reruns with the same q do not re-answer."""
    state["ask_answered_q"] = q


def reset_conversation(state: MutableMapping) -> None:
    """New conversation: drop the answered-question marker, clear the cross-feature evidence
    store, and request a deferred clear of the (widget-backed) Ask input."""
    state.pop("ask_answered_q", None)
    state["session_evidence"] = {}
    state["_pending_clear_ask"] = True


def apply_pending_clear(state: MutableMapping) -> None:
    """Apply a deferred Ask-input clear at top-of-script, BEFORE the ``ask_q`` widget exists
    (Streamlit forbids mutating a widget-backed key after its widget is instantiated)."""
    if state.pop("_pending_clear_ask", False):
        state["ask_q"] = ""
