# Task 4 — Benchmark coverage check (guideline-sensitivity)

**Date:** 2026-06-29
**Manifest:** `evaluation/inputs/benchmark-manifest.jsonl` (67 enabled questions, benchmark_version frozen)

## Method

Classified each question as management/evidence (guideline-sensitive: indications,
thresholds, timing, patient selection, classification, dosing, first-line, reversal,
prophylaxis) vs anatomy/technique (anatomy, approach, landmark, exposure, course/relationship).

## Result

| Bucket | Count |
|---|---|
| MGMT (guideline-sensitive, keyword) | 51 |
| BOTH (mgmt + anatomy keywords) | 1 |
| OTHER (no keyword, but on inspection all are management/outcomes — "which patients benefit", "do robotics/AI improve outcomes", "optimal management/strategy") | 15 |
| ANAT (pure anatomy/technique) | 0 |

Domains (all 7 represented): Neurointerventional 8, Spine 9, Brain Tumor 9, General 11,
Open Cerebrovascular 10, Functional 10, Trauma 10.

## Decision

**Use the frozen 67-question benchmark as the A/B target. Skip Step 3 (no new question set.)**

Rationale: the benchmark is ~100% management/evidence — it vastly exceeds the ~15
guideline-sensitive threshold, so it is well-suited to measure guideline *lift*. Reusing it
keeps the established baseline methodology and the one-variable discipline (no second,
un-baselined question set).

## Nuance recorded (not a blocker)

The benchmark has **no pure-anatomy guardrail questions** (0 ANAT). Dilution is still
detectable: the Task 5 **per-question regression scan** compares each question baseline vs
treatment, and the subset of management questions that guidelines do **not** improve serve as
the implicit non-inferiority guardrail. If those regress in the treatment arm, that is the
dilution signal the graduation rule requires.

## A/B target for Task 5

`QSET = evaluation/inputs/benchmark-manifest.jsonl` (all 67 ids, both arms).
