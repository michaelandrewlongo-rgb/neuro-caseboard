# Neuro·Caseboard Benchmark Evaluation Framework

A reproducible, benchmark-driven improvement system built around the 67-question
*Contemporary Questions in Neurosurgery* benchmark. It generates a frozen baseline of
Neuro·Caseboard answers, grades them against a practicing-neurosurgeon rubric, attributes failures
to specific pipeline components, implements targeted improvements, and reruns the benchmark to prove
genuine improvement without regressions.

This framework was produced and is driven by `project-loop` (state under `.project-loop/`).

## Layout

```
evaluation/
  inputs/        # the three source files, preserved verbatim (+ sha256 fidelity record), and the
                 # normalized machine-readable benchmark manifest + per-source provenance
  schemas/       # JSON Schemas for manifest / run-record / grade-record / defect-record
  scripts/       # deterministic runner, grader, analysis, and validation scripts
  runs/          # immutable run directories: baseline-<ts>/ and post-improvement-<ts>/
  reports/       # human-readable analysis: audit, summaries, failure analysis, priority matrix,
                 # root-causes/, tickets/, implementation plan, final comparison, residual risks
  experiment-ledger.md   # one entry per intervention (before/after, keep/revert decisions)
  failure-ledger.jsonl   # atomic defect records (controlled taxonomy)
```

## Inputs (verbatim, do not edit)

- `inputs/contemporary-qs-in-neurosurgery` — 67 questions across 7 sections.
- `inputs/nsgy-questioner.txt` — the batch question-runner protocol.
- `inputs/nsgy-grader.txt` — the practicing-neurosurgeon grading rubric (authoritative).

Fidelity is recorded in `inputs/SOURCE_CHECKSUMS.txt` (sha256 of each original == its copy).

## Stable question IDs

Section numbering restarts each section, so stable IDs are assigned by section:

| Section | Prefix | Count |
|---|---|---|
| Neurointerventional Surgery | `NIS-01..08` | 8 |
| Spine Surgery | `SPINE-01..09` | 9 |
| Brain Tumor Surgery | `TUMOR-01..09` | 9 |
| General Neurosurgery | `GENERAL-01..11` | 11 |
| Open Cerebrovascular Surgery | `OPEN-CV-01..10` | 10 |
| Functional Neurosurgery | `FUNCTIONAL-01..10` | 10 |
| Trauma Neurosurgery | `TRAUMA-01..10` | 10 |
| **Total** | | **67** |

## Citation faithfulness / groundedness metric

For each Ask answer the engine computes a per-answer `verification` summary: every claim that cites a
textbook `[n]` or literature `[L#]` marker is checked against its cited source by the entailment
verifier (`neuro_caseboard/entailment.py`), and the summary records `n_cited_claims`, `n_unsupported`,
`groundedness`, and the `unsupported_markers`. It is written to each run record under `verification`
(optional/`null` on error rows; see `schemas/run-record.schema.json`). `summarize_grades.py`
aggregates these into a `groundedness` block (overall and per domain) whose denominator is only the
answers that actually cite — fields `mean_groundedness`, `mean_unsupported_rate`, and
`fraction_with_unsupported`. `build_failure_ledger.py --run <run.jsonl>` turns answers with
unsupported claims into `unsupported_claim` defect records. The CLI prints a `needs-verification`
notice after the answer, gated by the `CASEBOARD_VERIFY_DISPLAY` env var (default on; set `=0` to
silence) — the verdicts are still computed regardless and are exposed in the API `verification`
response field and the run records.

## Reproduction

Exact commands are recorded in the root-level `NEURO_CASEBOARD_EVALUATION.md` once the runner,
grader, and analysis steps land. Each `runs/<...>/` directory carries its own immutable config
manifest (git commit, model/provider, corpus fingerprint, dependency-lockfile hashes) so any run can
be reproduced and compared.

## Ground rules (frozen)

- Only the three source files above + this local repo are used; no external research informs grades.
- The benchmark, grader rubric, prompts, model settings, and corpus are never changed between the
  baseline and the comparison run.
- Grades, citations, source verification, and test results are never fabricated. When current
  evidence cannot be checked, the affected grading dimension is labeled `verification_unavailable`.
