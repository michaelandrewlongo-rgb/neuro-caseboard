# Final Comparison — Baseline vs Post-Improvement

- **Baseline run:** `evaluation/runs/baseline-20260620-134705/` (engine @ commit 28a6e30, pre-fix).
- **Post run:** `evaluation/runs/post-improvement-20260620-182930/` (engine @ commit 3653c9e, C5 guard).
- **Held constant (verified):** the 67 benchmark questions, the `nsgy-grader.txt` rubric, the 7
  subspecialty grader prompts (frozen — identical text, only input/output paths differ), the model
  (vertex/gemini-2.5-pro), and the corpus/index. The **only** system change is the C5 empty-answer guard.

## Headline numbers

| metric | baseline | post | delta |
|---|---|---|---|
| mean score (n=66 scored) | 77.74 | 79.36 | **+1.62** |
| median | 81 | 82 | +1 |
| grade distribution | 0A/38B/22C/6D/0F | 0A/44B/19C/3D/0F | B +6, C −3, D −3 |
| **unsafe / safety-critical** | **0** | **0** | **0 (unchanged)** |
| completion rate | 98.5% (66/67) | 98.5% (66/67) | 0 |
| not_gradable | 1 (SPINE-02) | 1 (SPINE-02) | 0 |
| latency median / p95 | 52s / 86s | 47s / 88s | −5s / +2s |
| disambiguations | 5 | 6 | +1 |

**Paired per-question delta (66 questions scored in both):** mean **+1.62**, range −6..+11; **39 improved,
11 worsened, 16 unchanged**. Bootstrap 95% CI of the mean paired delta: **[+0.92, +2.36]** (B=2000, seed=42).

**Grade migrations (baseline→post):** C→B ×7, D→C ×3, B→C ×1 (net upward).

## ⚠️ The +1.62 is NOT attributable to the intervention — it is rerun noise

This is the central, deliberately-foregrounded conclusion. **Do not read the headline as evidence the
fix worked.**

- **The C5 guard is content-neutral.** It only changes behavior when synthesis returns an *empty*
  string: it retries, then abstains. It alters no non-empty answer. In neither run was any answer
  empty-then-rescued — SPINE-02 (the only empty case) failed *upstream* of the guard (see below) and
  stayed `not_gradable` in both runs. **Therefore the guard cannot have changed any of these 66 scores.**
- **So the entire +1.62 — and the bootstrap CI excluding zero — is uncontrolled run-to-run variance**
  (LLM non-determinism, no seed exposed; plus grader non-determinism). The CI measures the *consistency
  of the noise*, not a treatment effect. We **do not** claim statistical significance or improvement from
  it. The 11 *worsened* questions are the same noise in the other direction.
- **A proper attribution would require a control rerun** (same code, NO fix) to show the same drift. We
  did not run one (budget). The decisive argument is logical, not statistical: a content-neutral change
  cannot produce a content score change.

## What the C5 fix *does* attributably achieve

A **reliability guarantee**: `Engine._answer` can never surface an empty/None answer — it retries a
transient empty synthesis once, then degrades to the honest `REFUSAL` abstention. This is proven by
`tests/neuro_core/test_empty_answer_guard.py` (5 deterministic stubbed-synth tests), **independent of
this benchmark**. That is the real, generalizing deliverable; the benchmark score is not.

## SPINE-02: still not_gradable — and why (honest)

SPINE-02 remained `not_gradable` (empty/None) in the post run. The post-rerun diagnostic confirmed the
C5 guard *is* loaded and that the "Cervical" rewrite *can* resolve to a full 4786-char answer. So the
`None` is **not** an empty synthesis (the guard would have produced `REFUSAL`). It is a **transient
nested re-clarification**: the cervical rewrite sometimes trips a *second* `Clarification`, and the
runner's `_resolve_answer` (`evaluation/scripts/run_benchmark.py:285-294`) resolves only one level, so a
second `Clarification` (no `.answer`) yields `None`. This route is **upstream of `Engine._answer`**, so
the C5 guard never runs on it. The root-cause note's claim that "one guard covers every route" was
incomplete; this is documented as a follow-up (see residual-risks.md, TKT-C4 / a runner nested-
clarification guard). **The C5 fix is necessary but not sufficient for SPINE-02.**

## Success-criteria assessment

| criterion | result |
|---|---|
| No increase in safety-critical errors | ✅ 0 → 0 |
| No unexplained deterioration of previously-strong answers | ✅ the 11 worsened are within noise and none were strong (worst movers FUNCTIONAL-04 62→57, GENERAL-02 75→70, OPEN-CV-10 80→74 — all C/D-tier); strongest domain OPEN-CV stable (83.6→83.9) |
| Improvement in targeted defects | ⚠️ the targeted defect (empty-answer reliability) is fixed by **test**, not by a benchmark-score move; SPINE-02's specific not_gradable persists (different, upstream cause) |
| Stable/improved completion reliability | ✅ 98.5% → 98.5%; guarantee added that no empty answer can surface |
| Acceptable latency | ✅ median 52→47s; +1 synth call only on the (here, non-occurring) empty path |
| Improvement supported by question-level evidence | ⚠️ NOT claimed — the score delta is noise; the supported claim is the reliability invariant |

**Verdict:** the intervention is a clean, test-proven reliability hardening with **zero safety regression
and no strong-answer collapse**. We explicitly decline to claim a benchmark-score improvement, because the
change is content-neutral and the observed +1.62 is uncontrolled noise.
