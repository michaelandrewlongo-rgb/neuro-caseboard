# Neuro·Caseboard — Benchmark Evaluation & Improvement

A reproducible, benchmark-driven evaluation of the Neuro·Caseboard "Ask the corpus" engine against the
67-question *Contemporary Questions in Neurosurgery* benchmark, plus one test-proven reliability fix.
Full framework + artifacts under [`evaluation/`](evaluation/).

## What was evaluated

All 67 benchmark questions were answered by the **real engine** (in-process
`neuro_caseboard.qa.answer_question(force=True)`, vertex/gemini-2.5-pro, live LanceDB corpus) and
graded against the supplied `nsgy-grader.txt` rubric by **7 parallel subspecialty Claude graders**
(deliberately not the gemini answer-model, to avoid self-grading bias). Nothing was fabricated; where
current evidence couldn't be checked, grading dimensions are labeled `verification_unavailable`.

**Baseline (`evaluation/runs/baseline-20260620-134705/`):** mean **77.74** / median 81 (n=66 scored),
distribution 0A/38B/22C/6D/0F + 1 not_gradable, **0 unsafe answers**, 98.5% completion. Strongest domain
Open Cerebrovascular (83.6); weakest Functional (74.7).

## What was changed

**One production change:** `neuro_core/query.py::Engine._answer` — an **empty-answer guard** (CHG-C5).
A transient empty Gemini `resp.text` previously surfaced as a blank, not-gradable answer because
`is_refusal("")` is False and no empty guard existed. The engine now retries the synthesis once and, if
still empty, degrades to the honest `REFUSAL` abstention — so it can **never** return an empty/None
answer. Diff: 10 insertions, 1 deletion. Proven by `tests/neuro_core/test_empty_answer_guard.py` (5
deterministic stubbed-synth tests). Intervention #2 was **deliberately skipped** (documented) to keep the
before/after attributable.

## What measurably improved — and the honest caveat

Post-improvement rerun (`evaluation/runs/post-improvement-20260620-182930/`) mean **79.36** (+1.62 vs
baseline; paired bootstrap 95% CI [+0.92, +2.36]); D-grades halved (6→3); 0 unsafe (unchanged).

**This score delta is NOT attributable to the fix and we do not claim it as an improvement.** The C5
guard is content-neutral (it only rescues empty answers; none occurred-and-were-rescued in either run),
so it cannot have moved any of these 66 scores. The +1.62 — CI and all — is **uncontrolled run-to-run
noise** (LLM non-determinism, no seed; plus grader non-determinism). See
[`evaluation/reports/final-comparison.md`](evaluation/reports/final-comparison.md).

**What *is* attributably achieved:** a reliability **guarantee** (no empty answer can ever surface),
established by a benchmark-independent unit test. That is the real deliverable; the benchmark number is
not.

## What worsened

Nothing safety-relevant: 0 → 0 unsafe/safety-critical; the strongest domain (OPEN-CV) was stable
(83.6→83.9). 11 of 66 questions scored lower on the rerun (e.g. FUNCTIONAL-04 62→57) — this is the same
LLM/grader noise as the improvements, not a regression caused by the change.

## What remains unresolved

- **Corpus evidence-currency (C1, 60% of all defects, DEFERRED):** the textbook corpus predates the
  2022–2025 practice-changing trials (ESCAPE-MeVO, SELECT2, the MMA RCTs, ENRICH, SANTE, RESCUEicp,
  GFAP/UCH-L1, SLIP/NORDSTEN, JLGK0901). This is the dominant score driver and is **not fixed**; the
  generalizing remediation is a literature-retrieval lane (`neuro_caseboard/literature/`), a separate
  effort. (TKT-C1)
- **SPINE-02 still not_gradable:** caused by a *transient nested re-clarification* the runner resolves
  only one level deep — upstream of the C5 guard. The C5 fix is necessary but not sufficient here; the
  follow-up is a runner/decomposition guard. (TKT-C4 / R5)
- C2 (decision-coverage), C3 (calibration), C4 (mis-scoping) remain open tickets.

## Strongly-supported vs uncertain conclusions

**Strongly supported:** the engine is **clinically safe** on this benchmark (0 unsafe across 67, both
runs); its failure mode is **currency/completeness, not danger**; the C5 reliability guard is correct and
test-proven. **Uncertain / explicitly not claimed:** any benchmark *score* improvement from the fix (it's
noise); **generalization to unseen questions** — a single 67-item set with no held-out split *cannot*
establish this (see [`evaluation/reports/residual-risks.md`](evaluation/reports/residual-risks.md)); a
disjoint held-out set is the required next experiment.

## Reproduce

```bash
WT=$(git rev-parse --show-toplevel)
export PYTHONPATH="$WT:$WT/vendor/caseprep"      # no venv; shadows the worktree's code

# 1. Validate the benchmark (exactly 67, verbatim) + run the regression harness (218 tests)
python3 -m pytest -q tests/neuro_core tests/test_pipeline.py tests/test_retrieve.py tests/test_qa.py tests/evaluation

# 2. Rebuild the 67-question manifest from the verbatim source (deterministic)
python3 evaluation/scripts/build_manifest.py
python3 evaluation/scripts/validate_manifest.py

# 3. Run the benchmark (needs Vertex ADC + GOOGLE_CLOUD_PROJECT + the LanceDB index; ~65 min)
python3 evaluation/scripts/run_benchmark.py --run-dir evaluation/runs/<new-run> --timeout 300
python3 evaluation/scripts/finalize_run.py --run-dir evaluation/runs/<new-run>
# grading is performed by 7 subspecialty LLM graders → grades/*.jsonl, then:
python3 evaluation/scripts/summarize_grades.py --run-dir evaluation/runs/<new-run> --out-prefix <prefix>

# 4. Rebuild the failure ledger from grades
python3 evaluation/scripts/build_failure_ledger.py --grades evaluation/runs/<run>/<prefix>-grades.jsonl --out evaluation/failure-ledger.jsonl
```

## Artifact index

| Artifact | Path |
|---|---|
| Framework README | `evaluation/README.md` |
| Repository audit | `evaluation/repository-audit.md` |
| Benchmark manifest (67, verbatim) | `evaluation/inputs/benchmark-manifest.jsonl` |
| Schemas | `evaluation/schemas/*.schema.json` |
| Scripts (runner, grader-summary, ledger, finalize) | `evaluation/scripts/` |
| Baseline run + grades + summary | `evaluation/runs/baseline-20260620-134705/` |
| Post-improvement run + grades + summary | `evaluation/runs/post-improvement-20260620-182930/` |
| Failure ledger (406 defects) | `evaluation/failure-ledger.jsonl` |
| Failure analysis / priority matrix | `evaluation/reports/{failure-analysis,priority-matrix}.md` |
| Root-cause notes | `evaluation/reports/root-causes/` |
| Tickets / implementation plan | `evaluation/reports/tickets/`, `evaluation/reports/implementation-plan.md` |
| Experiment ledger | `evaluation/experiment-ledger.md` |
| Final comparison / residual risks | `evaluation/reports/{final-comparison,residual-risks}.md` |
| Production fix | `neuro_core/query.py` + `tests/neuro_core/test_empty_answer_guard.py` |
