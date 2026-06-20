# TKT-C5 — Disambiguated/narrowed re-call can surface an empty (not-gradable) answer

- **Failure-mode ID / category:** C5 / `disambiguation_failure` + `engine_reliability`
- **Severity / priority:** material / **P0** (priority 200; highest fixability-per-impact)
- **Labels:** `severity:material` `subsystem:synthesis` `subsystem:query` `stage:answer` `status:in-progress`
- **Affected benchmark questions:** SPINE-02 (the only `not_gradable` in the baseline). Latent risk for **any** question (the empty-text path is query-agnostic).
- **Artifact links:** `evaluation/reports/root-causes/C5-disambiguation-empty-answer.md`, `evaluation/runs/baseline-20260620-134705/run.jsonl` (SPINE-02), `evaluation/reports/failure-analysis.md` (C5), `evaluation/reports/priority-matrix.md`.

## Representative evidence
SPINE-02 → `status=not_gradable`, `error_details="engine returned an empty/None answer"`, `selected_variant="Cervical"`, latency 93.2s.

## Observed vs expected
- **Observed:** the synthesis client returned an empty string (transient Gemini empty `resp.text`); it propagated unguarded to the user as a non-answer.
- **Expected:** the engine must never surface an empty/None answer — it should either produce a real answer (retry the transient failure) or return the honest abstention (`REFUSAL`), which is *gradable*.

## Clinical / product impact
A blank answer to a real clinical question is the worst UX failure mode (worse than an honest "not found"). It is also the only outright benchmark non-answer.

## Suspected layer & causal confidence
synthesis robustness / infra, surfaced by a missing empty-answer guard. **Causal confidence: high** (live reproduction: identical rewrite re-ran to a full 3868-char/15-citation answer; retrieval healthy at 12 passages, top score 0.98 — so transient, not structural).

## Reproduction
```
PYTHONPATH=<wt>:<wt>/vendor/caseprep python3 -c "
from neuro_core.synthesize import synthesize  # path under test
# Drive Engine._answer with a synth_fn stubbed to return '' once then a real answer;
# assert the engine never returns an empty answer (retry path), and returns REFUSAL if empty twice."
```
The defect is transient with the live model; the regression test uses a **stubbed synth** to force the empty path deterministically (no live model needed).

## Acceptance criteria
1. `Engine._answer` never returns an answer that is empty/whitespace-and-not-a-refusal.
2. On a transient empty synth result, it retries once; if the retry yields content, that content is returned.
3. If still empty, it returns `REFUSAL` with empty citations/figures (gradable abstention), not `""`.
4. Existing harness stays green (213) and the live SPINE-02 path no longer yields `not_gradable` (best-effort live re-check in step 9/11).

## Regression-test requirements
A new unit test in `tests/neuro_core/` driving `Engine._answer` (or its synth seam) with a stubbed `synth_fn`: (a) empty-then-content → returns content, attempts retry; (b) empty-then-empty → returns `REFUSAL`; (c) a normal non-empty answer is unchanged; (d) an actual refusal string is still treated as refusal. Added to the harness.

## Out of scope (separate ticket)
The narrowing that dropped the lumbar limb of SPINE-02 → **TKT-C4-mis-scoping** / query_decomposition. Not fixed here.
