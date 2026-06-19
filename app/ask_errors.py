"""Actionable error handling for Ask submissions (BACKLOG P3 #9).

Pure helpers (no Streamlit) so the classification + failure-gating logic is unit-testable. The app
wraps ``answer_question`` and, on failure, shows ``classify_error``'s message, preserves the query,
and offers Retry. A per-question failure marker prevents an auto-retry storm on every rerun."""
from __future__ import annotations

import logging
from typing import MutableMapping

_log = logging.getLogger("neuro_caseboard.ask")

# (exception types, kind, actionable message). First match wins; order specific -> general.
_ERROR_HINTS = [
    (TimeoutError, "timeout",
     "The search timed out — the corpus may be cold or the question very broad. "
     "Retry, or narrow the question."),
    ((ConnectionError, OSError), "network",
     "Couldn't reach a backend service (retrieval or literature). "
     "Check connectivity and retry."),
]


def classify_error(exc: BaseException) -> tuple[str, str]:
    """Map an exception to (kind, actionable message)."""
    for types, kind, msg in _ERROR_HINTS:
        if isinstance(exc, types):
            return kind, msg
    return ("error",
            f"Something went wrong while answering ({type(exc).__name__}). "
            "Your question is preserved — please retry.")


def log_failure(stage: str, exc: BaseException) -> None:
    """Record a stage-specific failure for debugging."""
    _log.error("ask failure at stage=%s: %s: %s", stage, type(exc).__name__, exc)


def not_yet_failed(state: MutableMapping, q: str) -> bool:
    """True unless ``q`` already failed and is awaiting an explicit Retry (prevents auto-retry
    on every rerun while still preserving the query)."""
    return state.get("ask_failed_q") != q


def note_failure(state: MutableMapping, q: str, message: str) -> None:
    state["ask_failed_q"] = q
    state["ask_error"] = message


def clear_failure(state: MutableMapping) -> None:
    state.pop("ask_failed_q", None)
    state.pop("ask_error", None)
