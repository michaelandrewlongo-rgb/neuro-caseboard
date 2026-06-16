# LOOP_LOG — Case Dossier engine (`caseboard case`)

Self-driving build log (see `LOOP_PROMPT.md`). One line per pass: pass #, increment, test result,
eval/judge score before→after, next bottleneck.

| pass | increment | tests | eval (before→after) | next bottleneck |
|---|---|---|---|---|
| 1 | WS-1 `CaseContext` + dictation intake (`case_context.py`, `intake.py`) | 400 passed, 1 skipped (was 383; +17 new, 0 regressions) | intake eval 6/6 side · 6/6 level · 6/6 goal · 6/6 comorbid · `missing_critical` ≤3 all / ==0 on complete (was n/a → MET) | WS-2: expand section taxonomy to the 8 case surfaces (model.py + compile.py + Explorer), topic-agnostic, single evidence axis |

## Notes

- **Pass 1 (2026-06-16, WS-1).** Built the structured intake foundation: `CaseContext` dataclass
  (geometry/history/plan + `to_topic()` bridge to the existing pipeline, `missing_critical()` capped
  at 3) and an LLM-first `intake.parse_dictation` (injected `complete_fn`, graceful fallback) with a
  topic-agnostic `deterministic_parse` (age/sex/laterality/level — handedness-aware, disc-range
  preferred over single root level). Offline tests (`test_case_context.py` ×6, `test_intake.py` ×11)
  + a reproducible offline eval (`eval/case_dictations.json`, `eval/intake_eval.py` →
  `eval/CASE_INTAKE_REPORT_2026-06-16.md`). Two bugs the eval caught and fixed in-loop: handedness
  ("right-handed") polluting lesion laterality; single root level ("C6") winning over the disc range
  ("C5-6"). Live model-quality blind grade deferred — no provider key in this environment.
  No new runtime dependency; `caseboard` entry point still imports on core deps.
