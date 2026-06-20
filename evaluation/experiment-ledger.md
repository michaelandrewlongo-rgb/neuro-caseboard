# Experiment Ledger

One entry per intervention. Before/after metrics, keep/revert decisions, evidence.

---

## CHG-C5-empty-answer-guard  (intervention #1) — **KEEP**

- **Ticket / defect:** TKT-C5 / disambiguation_failure + engine_reliability (SPINE-02 not_gradable + latent empty-answer risk for all queries).
- **Files changed:**
  - `neuro_core/query.py` — `Engine._answer`: empty-but-not-refusal synth result → retry `synth_fn` once; if still empty → return `REFUSAL` (gradable abstention). Added `REFUSAL` to the `synthesize` import.
  - `tests/neuro_core/test_empty_answer_guard.py` — 5 deterministic stubbed-synth tests (added to harness).
- **Hypothesis:** a transient empty/whitespace synth result (Gemini candidate with no text part) surfaces as a blank not-gradable answer because `is_refusal("")` is False and no empty guard exists; a retry-then-REFUSAL guard eliminates the blank.
- **Before metrics:** harness 213 pass; new test RED (3 fail / 2 pass); SPINE-02 = not_gradable in baseline.
- **After metrics:** harness **218 pass / 0 fail** (213 + 5 new); new test GREEN (5/5); `Engine._answer` provably never returns empty-non-refusal (deterministic proof).
- **Questions expected to improve:** SPINE-02 (blank → real answer or gradable abstention); removes a latent reliability failure class for all questions.
- **Questions worsened:** none. The guard triggers ONLY when the answer is empty/whitespace; normal answers and genuine refusals take the identical pre-existing path (verified by `test_normal_answer_is_unchanged_and_not_retried` and `test_literal_refusal_is_preserved_and_not_retried`). Sentinels (OPEN-CV-01..10, SPINE-08, GENERAL-06, NIS-06, TUMOR-07/09) are structurally unaffected.
- **Safety-critical changes:** none introduced; safety-POSITIVE (a blank clinical answer becomes either a real answer or an explicit "Not found in the provided sources").
- **Latency changes:** +1 synth call ONLY on the rare empty path; zero change on the normal path.
- **Decision:** **KEEP** — supported root cause, measurable outcome (218 green, deterministic empty-path proof), regression test present, clean single-commit rollback.
- **Evidence:** TDD red→green transcript; harness 218 pass; root-causes/C5-disambiguation-empty-answer.md (live reproduction). Live end-to-end confirmation deferred to the step-11 full rerun (SPINE-02 re-answered under the patched engine).
- **Rollback:** `git revert` the step-9 commit (change confined to `_answer` + one test file; no schema/config/corpus change).
