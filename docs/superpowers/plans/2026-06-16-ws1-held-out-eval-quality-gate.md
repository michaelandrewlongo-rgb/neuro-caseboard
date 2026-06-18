# Plan — WS-1: Held-out eval set + quality-regression gate (test-first)

Spec: `docs/superpowers/specs/2026-06-16-ws1-held-out-eval-quality-gate-design.md`.
Order is strict TDD: write the failing test, watch it fail, write the minimal code/data to pass.

## Tasks

1. **RED — dataset-shape tests.** Add `tests/test_quality_gate.py::test_eval_set_size_and_breadth`,
   `::test_split_partition`, `::test_dictations_mirror_cases`. Run → fail (only 6 cases, old split
   labels).
2. **GREEN — author the held-out eval set.** Expand `eval/cases.json` to 27 cases across 7
   subspecialties (4/4/4/4/3/4/4); rename split `dev`→`tune`, `holdout`→`eval`; tag new cases so the
   partition is ≈ 1/3 tune ÷ 2/3 eval, disjoint by id. Mirror every id in
   `eval/case_dictations.json` with dictation + ground_truth. Extend `eval/figure_spec_cases.json`.
   Run dataset tests → green.
3. **RED — gate behavior tests.** Add `::test_gate_deterministic`, `::test_gate_reads_only_eval_split`,
   `::test_gate_passes_on_committed_baseline`, `::test_gate_fails_when_metric_below_baseline`. Run →
   fail (no `eval/quality_gate.py`).
4. **GREEN — implement the gate.** Write `eval/quality_gate.py` (`load_split`, `compute_metrics`,
   `load_baseline`, `compare`, `main`) reusing the production engine + the canned PubMed lane from
   `case_eval`. Run gate tests except the baseline-pass one → green.
5. **GREEN — commit the baseline.** Run `python3 eval/quality_gate.py --emit-baseline > eval/BASELINE.json`
   (or hand-write from the measured table); confirm `python3 eval/quality_gate.py` exits 0. Run
   `::test_gate_passes_on_committed_baseline` → green.
6. **Wire CI.** Add the `python eval/quality_gate.py` step to `.github/workflows/ci.yml` `test` job
   (3.12 leg). Reproduce with `ci/local-ci.sh` if available.
7. **Verify.** Full `python3 -m pytest` green, 0 regressions vs baseline 451/1; `caseboard`
   still imports; `python3 eval/quality_gate.py` exits 0.
8. **Record.** Append one line to `LOOP_LOG.md`.

## Non-goals (this pass)
Raising any metric (WS-2…WS-5); LLM judges (WS-6); any safety feature.
