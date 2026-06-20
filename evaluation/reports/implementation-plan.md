# Implementation Plan — Improvement Interventions

Each change requires (per spec) a supported root cause, a measurable expected outcome, a regression
test, and a rollback path before any production code is edited.

---

## CHG-C5-empty-answer-guard  (SELECTED — intervention #1)

```yaml
change_id: CHG-C5-empty-answer-guard
ticket: TKT-C5
defects_addressed:
  - SPINE-02 not_gradable (empty answer); latent empty-answer risk for ALL queries
causal_evidence: >
  root-causes/C5-disambiguation-empty-answer.md — transient empty resp.text from Gemini
  (neuro_core/synth_clients.py:104, `resp.text or ""`) propagates unguarded because the only
  post-synthesis check is is_refusal(), and is_refusal("") is False (neuro_core/query.py:209).
  Live reproduction: identical input re-ran to a full 3868-char/15-citation answer (transient, not
  structural; retrieval healthy).
files_and_symbols:
  - neuro_core/query.py :: Engine._answer (lines ~204-217, the is_refusal seam)
  - neuro_core/synthesize.py :: REFUSAL (import the honest-abstention constant)
proposed_change: >
  In Engine._answer, after syn = self.synth_fn(...), if the answer is empty/whitespace AND not a
  refusal, retry synth_fn ONCE; if the retry is still empty, return
  QueryResult(answer=REFUSAL, citations=[], figures=[]) (a gradable abstention). Normal answers and
  genuine refusals are unchanged. Smallest sufficient change at the existing guard seam.
expected_benefit: >
  The engine can never surface an empty/None answer for any query. SPINE-02 converts from
  not_gradable to either a real answer (retry succeeds) or a gradable abstention. Removes the only
  baseline non-answer and a class of latent reliability failures.
possible_regressions:
  - A genuine, correct empty result (none expected — REFUSAL already covers "not found")
  - One extra synth call on the rare empty path (latency only on that path; bounded to +1 retry)
questions_expected_to_improve: [SPINE-02]
sentinel_questions_that_must_not_worsen: [OPEN-CV-01..10 (all B, strongest), SPINE-08, GENERAL-06, NIS-06, TUMOR-07, TUMOR-09]
unit_tests:
  - tests/neuro_core/test_empty_answer_guard.py: stub synth_fn → (a) empty-then-content returns content;
    (b) empty-then-empty returns REFUSAL; (c) normal answer unchanged; (d) literal refusal still refusal.
integration_tests:
  - existing harness (213) stays green
acceptance_criteria:
  - Engine._answer never returns empty-non-refusal; retry-once then REFUSAL; harness green; new unit tests pass
rollback_method: >
  git revert the single intervention commit. Change is confined to Engine._answer + one test file;
  no schema/config/corpus change, so revert is clean and isolated.
```

**Verification path (steps 9 & 11):** unit tests (deterministic, stubbed synth) + harness green; then a
best-effort live re-answer of SPINE-02 in the post-improvement run (step 11) to confirm the non-answer
is gone. The fix is model-agnostic, so the deterministic unit test is the primary proof; the live
re-check is confirmatory.

---

## CHG-C3-calibration  (CANDIDATE — intervention #2, budget permitting)

```yaml
change_id: CHG-C3-calibration
ticket: TKT-C3
defects_addressed: [38 overabsolute_language defects]
causal_evidence: root-causes/C2-synthesis-completeness.md + failure-analysis.md (C3); synthesis prompt lacks a calibration instruction
files_and_symbols: [neuro_core synthesis prompt assembly (confirm exact symbol in step 10)]
proposed_change: add a narrow calibration instruction to qualify claims where evidence is mixed/evolving
expected_benefit: reduced over-absolute phrasing; better calibrated-uncertainty score
possible_regressions: over-hedging that weakens genuinely settled recommendations (guard with sentinels)
questions_expected_to_improve: [questions with overabsolute_language defects]
sentinel_questions_that_must_not_worsen: [OPEN-CV-01..10, SPINE-08, GENERAL-06]
unit_tests: [prompt-assembly unit test asserting the calibration clause is present]
integration_tests: [harness green]
acceptance_criteria: over-absolute phrasing reduced on affected Qs; no degradation of strong answers; no latency/safety regression
rollback_method: git revert the single commit (prompt-only change)
```
**Status:** candidate; confirm exact prompt symbol + decide scope in step 10. Prefer over C2 (narrower, lower-risk).

---

## DEFERRED (documented, not implemented this pass)

- **CHG-C1-literature-currency (TKT-C1):** enable/strengthen the PubMed literature lane to inject
  2022–2025 evidence into synthesis. Highest impact, but large + network-dependent + latency/regression
  risk → deferred to its own focused effort. Concrete surface: `neuro_caseboard/literature/`.
- **CHG-C2-decision-coverage (TKT-C2):** prompt requirement to enumerate thresholds/comparators/risks —
  risks broad prompt rewrite + overlaps C1.
- **CHG-C4-decomposition (TKT-C4):** stop splitting coordinated "A and/or B" questions
  (`query_analyze.py`); deeper query-understanding change. The C5 guard already removes the non-answer
  symptom, lowering C4's urgency.
