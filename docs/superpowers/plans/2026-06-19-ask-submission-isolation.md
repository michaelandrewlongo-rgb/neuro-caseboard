# Ask Submission Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each Ask submission an isolated, single-shot query: answer once per submission (not on every rerun), bind retrieval strictly to the current question, clear the input after submission, and add an explicit "New conversation / Clear context" control — so Ask never re-answers stale questions or carries earlier topics forward (BACKLOG P1 #2).

**Architecture:** The engine is already per-query stateless — `neuro_caseboard.qa.answer_question(q)` runs Lane A `neuro_core.query.query(q)` and Lane B `build_literature_section(q)`, each seeing only the current question. The leakage is in the Streamlit app layer (`app/streamlit_app.py`): `ask_q` is a persistent widget whose non-empty value re-invokes `answer_question(q)` on every rerun; the input is never cleared; and the session-scoped `session_evidence` store accumulates `EvidenceRef`s across all submissions (the "also in …" cross-feature badges). Fix: extract the isolation/reset logic into a **pure, hermetically-testable helper** `app/ask_session.py` (operates on a plain `session_state`-like mapping), then wire it into the Ask lane so a submission answers once, the engine is called with exactly the current query, the input clears, and a "New conversation / Clear context" button resets Ask state.

**Tech Stack:** Python 3.10+, Streamlit 1.56.0 (`streamlit.testing.v1.AppTest`, `session_state`), pytest. Hermetic tests — no corpus / LLM / retriever / network (the engine call is stubbed/injected).

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_ask_submission_isolation.py`. Full suite is ~17min on WSL2 — keep the inner loop scoped to this file; CI runs the full suite.
- Presentation/app-layer change only: do NOT modify `neuro_caseboard/` or `neuro_core/` engine modules. `answer_question`/`query`/`build_literature_section` already bind to the current query; the fix is in `app/`.
- `app/` is a bare-import script dir (no `__init__.py`); new modules import bare (e.g. `from ask_session import ...`) matching `signal_theme`/`figure_gallery`. Tests must `sys.path.insert(0, app/)`.
- Streamlit rule: a widget-backed `session_state` key (e.g. `ask_q`) cannot be mutated after its widget is instantiated. Clear it via the existing pending-seed pattern (set a pending flag, apply it at top-of-script BEFORE the widget is created) — mirror the `_pending_mode`/`seed_question` handling at `app/streamlit_app.py:48-53`.
- Tests must be hermetic: stub the engine (`answer_question`) and drive pure helpers on a dict; never touch the corpus/LLM/network. No new dependencies.
- Verified facts: Ask lane is `app/streamlit_app.py:71-121`; `q = st.text_input(..., key="ask_q")`; `result = answer_question(q)` runs whenever `q` is truthy; `_store = st.session_state.setdefault("session_evidence", {})` (line 56); cross-flow seeds use the pending pattern (lines 48-53); `answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None)` (qa.py:103).

---

## Tasks (project-loop step cursor)

The loop's `step_cursor` indexes these two items only.

- [x] Task 1: Pure Ask-isolation session helpers (`app/ask_session.py`) + hermetic unit tests
- [x] Task 2: Wire the helpers into the Ask lane (submit-once, clear input, New-conversation control, current-query binding) + AppTest boot smoke

---

### Task 1: Pure Ask-isolation session helpers + hermetic unit tests

**Files:**
- Create: `app/ask_session.py`
- Create (Test): `tests/test_ask_submission_isolation.py`

**Interfaces:**
- Produces:
  - `is_new_submission(state: MutableMapping, q: str) -> bool` — True iff `q` is non-empty and differs from `state.get("ask_answered_q")`. This makes the lane answer once per distinct submission instead of on every rerun.
  - `mark_answered(state: MutableMapping, q: str) -> None` — record `state["ask_answered_q"] = q` so subsequent reruns of the same `q` do not re-answer.
  - `reset_conversation(state: MutableMapping) -> None` — clear Ask context: pop `ask_answered_q`, clear `session_evidence` (to `{}`), and set `state["_pending_clear_ask"] = True` (the script applies it to the `ask_q` widget key at top-of-run, before the widget exists).
  - `apply_pending_clear(state: MutableMapping) -> None` — if `state.pop("_pending_clear_ask", False)`, set `state["ask_q"] = ""`. Called at top-of-script (pending-seed pattern) before the Ask widget is instantiated.
- Consumes: nothing from earlier tasks.

**Verified facts (hold while writing the test):**
- These helpers operate on any `MutableMapping` (a plain `dict` in tests; `st.session_state` in the app), so they are fully hermetic — no Streamlit, engine, or network.
- `session_evidence` is a `dict` (`EvidenceRef.key -> set[str]`); `reset_conversation` replaces it with a fresh `{}` so prior-question cross-refs cannot bleed into a new conversation.

**Step 1: Write the failing test**

Create `tests/test_ask_submission_isolation.py`:

```python
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
```

**Step 2: Run the test to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_submission_isolation.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ask_session'`.

**Step 3: Write the minimal implementation**

Create `app/ask_session.py`:

```python
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
```

**Step 4: Run the test to verify it passes**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_submission_isolation.py`
Expected: PASS — 6 passed.

**Step 5: Commit**

```bash
git add app/ask_session.py tests/test_ask_submission_isolation.py
git commit -m "loop step 0: pure Ask-isolation session helpers + hermetic unit tests"
```

---

### Task 2: Wire the helpers into the Ask lane + AppTest boot smoke

**Files:**
- Modify: `app/streamlit_app.py` (top-of-script pending-clear; Ask lane submit-once + clear-after-submit + New-conversation button)
- Modify (Test): `tests/test_ask_submission_isolation.py` (append an AppTest that the app boots and the engine is called with exactly the current query)

**Interfaces:**
- Consumes: `is_new_submission`, `mark_answered`, `reset_conversation`, `apply_pending_clear` from Task 1.
- Produces: nothing new (call-site wiring).

**Exact edits to `app/streamlit_app.py`:**

1. Add the bare import next to `from figure_gallery import figure_card` (top of file):

```python
from ask_session import (is_new_submission, mark_answered, reset_conversation,
                         apply_pending_clear)
```

2. In the top-of-script pending-seed block (after the `seed_topic` handling at lines 48-53, BEFORE the sidebar/widgets), apply any deferred Ask-input clear:

```python
apply_pending_clear(st.session_state)
```

3. Replace the Ask lane answer gate (currently `if q:` → unconditional `answer_question(q)`) so the engine runs once per distinct submission and the result persists across reruns. Add a "New conversation" control:

```python
    col_new, _ = st.columns([1, 4])
    with col_new:
        if st.button("New conversation", help="Clear the question, answer, and cross-references"):
            reset_conversation(st.session_state)
            st.rerun()
    if q and is_new_submission(st.session_state, q):
        with st.spinner("Searching textbooks + recent literature…"):
            result = answer_question(q)            # current query ONLY — no history concatenation
        st.session_state["ask_result"] = result
        mark_answered(st.session_state, q)
    result = st.session_state.get("ask_result")
    if q and result is not None:
        # ... existing rendering of result (Clarification check, figures, sources, literature, PDF) ...
```

(Keep the existing rendering body unchanged below the gate; it now reads `result` from session_state so reruns re-render without re-answering. The `Clarification` branch stays as-is.)

**Step 1: Write the failing test (append to `tests/test_ask_submission_isolation.py`)**

```python
def test_ask_lane_calls_engine_with_current_query_only(monkeypatch):
    """End-to-end app guard: asking a question calls answer_question with EXACTLY that string —
    never a history-concatenated prompt — and the app boots with no exception. Hermetic: the
    engine is stubbed, so no corpus/LLM/network is touched."""
    import neuro_caseboard.qa as qa
    calls = []

    class _Res:  # minimal QAResult stand-in
        answer = "stub answer"; citations = []; figures = []; literature = None

    def _fake_answer(question, **kw):
        calls.append(question)
        return _Res()

    monkeypatch.setattr(qa, "answer_question", _fake_answer)

    from streamlit.testing.v1 import AppTest
    app_py = str(APP_DIR / "streamlit_app.py")
    at = AppTest.from_file(app_py, default_timeout=30)
    at.session_state["ask_q"] = "borders of the cavernous sinus"
    at.run()
    assert len(at.exception) == 0
    assert calls == ["borders of the cavernous sinus"]
```

> Note on patch seam: the app does `from neuro_caseboard.qa import answer_question`, binding the name into the app module at import. Confirm the patch target during implementation — patch the name the app actually calls (either `monkeypatch.setattr` on the app module's `answer_question` after first import, or call through `qa.answer_question`). Adjust the test to whichever seam the wiring exposes; the load-bearing assertion is `calls == [current_query]`.

**Step 2: Run to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_submission_isolation.py::test_ask_lane_calls_engine_with_current_query_only`
Expected: FAIL before wiring (import error on `ask_session`, or engine called with the wrong/duplicated value).

**Step 3: Apply the edits above to `app/streamlit_app.py`.**

**Step 4: Run the full harness**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_submission_isolation.py`
Expected: PASS — 7 passed.

**Step 5: Commit**

```bash
git add app/streamlit_app.py tests/test_ask_submission_isolation.py
git commit -m "loop step 1: isolate each Ask submission (submit-once, clear input, New-conversation control)"
```

---

## Self-Review

**1. Spec coverage:** (1) each submission a new query by default → `is_new_submission`/`mark_answered` gate (answer once per distinct q). (2) New conversation/Clear context control → `reset_conversation` + button. (3) bind retrieval strictly to current query → engine already per-query; `test_ask_lane_calls_engine_with_current_query_only` guards it. (4) reliably clear input after submission → `_pending_clear_ask` + `apply_pending_clear` (the New-conversation path clears; submission-clear can reuse the same deferred mechanism). (5) wrong-context across sequential unrelated questions → `test_a_new_distinct_question_is_a_new_submission` + `test_reset_conversation_clears_prior_question_and_evidence` + the current-query-only AppTest. ✔
**2. Placeholder scan:** All steps contain runnable code/commands and exact expected output. The one ellipsis ("existing rendering body") refers to code already present in `app/streamlit_app.py:84-121` — not new code to write. ✔
**3. Type consistency:** helper signatures (`is_new_submission(state, q) -> bool`, `mark_answered(state, q)`, `reset_conversation(state)`, `apply_pending_clear(state)`) are identical between Task 1 (definition), the unit tests, and Task 2 (call sites). `session_evidence` stays a dict. ✔

> Open implementation question for Task 2 (resolve during wiring, not a plan gap): whether "clear input after submission" should fire on every submission or only via the New-conversation control. The spec lists both "treat each submission as a new query" and "reliably clear the input after submission" — if auto-clearing after each answer proves to fight Streamlit's widget lifecycle, prefer the explicit New-conversation control for clearing and keep submit-once gating for isolation; note the decision in the commit.
