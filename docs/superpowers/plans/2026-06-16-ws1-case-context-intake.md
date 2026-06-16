# WS-1: `CaseContext` + dictation intake — Implementation Plan

**Goal:** Turn a free-text clinical dictation into a structured, queryable `CaseContext`, with an
LLM-first intake layer (injected model fn) and a topic-agnostic deterministic fallback, plus a
`to_topic()` bridge to the existing pipeline. Offline-deterministic tests; no new core dep.

**Spec:** `docs/superpowers/specs/2026-06-16-ws1-case-context-intake-design.md`

**Conventions:** run tests with `python3 -m pytest` from the worktree root. Commits use
Conventional Commits ending with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
trailer. Branch: `worktree-streamlit-executive-navy-loop`.

---

## Task 1: `CaseContext` dataclass + helpers (test-first)
- Test: `tests/test_case_context.py` — `to_topic()`, `target()`, `from_dict()` coercion,
  `missing_critical()` (≤3, empty-when-complete).
- Impl: `neuro_caseboard/case_context.py`.
- Run: `python3 -m pytest tests/test_case_context.py -q` → green.

## Task 2: intake layer (test-first)
- Test: `tests/test_intake.py` — injected-fake LLM parse populates fields + merges deterministic
  floor; `_extract_json` tolerance; fallback on error / no-provider; deterministic regex
  extraction across cranial/spine/vascular; topic-agnostic guard (no clinical vocab leak).
- Impl: `neuro_caseboard/intake.py` (reuse `explore_llm._extract_json`, `_default_complete`,
  `llm_available`).
- Run: `python3 -m pytest tests/test_intake.py -q` → green.

## Task 3: EVAL harness + dictations
- `eval/case_dictations.json`: 6 dictations (reuse `cases.json` ids) + `ground_truth`.
- `eval/intake_eval.py`: deterministic parse → score side/level + assert `missing_critical()` ≤3;
  write `eval/CASE_INTAKE_REPORT_2026-06-16.md`.
- Run: `python3 eval/intake_eval.py`.

## Task 4: Verify + record
- Full offline suite: `python3 -m pytest -q` → green (no regression).
- Import gate: `python3 -c "import neuro_caseboard.cli, neuro_caseboard.case_context, neuro_caseboard.intake"`.
- Append the Pass-1 line to `LOOP_LOG.md`.
- Commit.
