# Guidelines A/B — Verdict (cheap stack)

**Date:** 2026-06-30
**Change under test:** 42 clinical guidelines added to the corpus (sandbox index, 60 sources)
vs the live 18-textbook corpus. **One variable** — both arms on the identical cheap stack
(`deepseek-v4-flash` synth + Vertex `gemini-2.5-flash` disambiguation). Frozen 67-Q benchmark.

## Verdict: DO NOT PROMOTE to live as-is. Keep guidelines held out.

On the cheap stack the guidelines produce **no statistically detectable quality improvement**
and introduce a **retrieval-crowding regression**. The live index stays at 18 textbooks.

## Numbers (blinded paired grading, 67/67)

| | value |
|---|---|
| mean baseline (18) | **84.07** |
| mean treatment (60) | **85.30** |
| mean paired delta | **+1.22** (sd 7.53, median +2.0) |
| significance | **t ≈ 1.33 → NOT significant** (p≈0.19) |
| head-to-head | treatment 36 / baseline 21 / tie 10 |
| new safety errors | 1 — in the **baseline** arm (TRAUMA-09, mannitol/HTS reversed); none in treatment |
| drift control | both arms graded fresh-blinded in one pass (no stale-baseline confound) |

Graders: 7 fellowship-trained subspecialty Claude graders, one per domain, blind to arm,
A/B order randomized per question (rubric `evaluation/inputs/nsgy-grader.txt`).

## Why not promote — three findings

1. **Lift is not attributable to the guidelines.** Questions whose treatment answer cited a
   guideline improved **+1.26**; questions that did not improved **+1.18** — essentially
   identical. The small positive delta is broadly distributed noise, not a guideline effect.
   (Attribution was real: guidelines were cited in **39/67** treatment answers, 96 citations —
   they are *not inert*, they just don't move graded quality.)

2. **Retrieval crowding — a real regression.** Worst question **TRAUMA-02: −44**. The
   supratentorial-TBI decompressive-craniectomy question was answered as *suboccipital
   decompression for cerebellar infarction* because the AHA Acute Ischemic Stroke 2026 (×3) and
   Spontaneous ICH 2022 (×2) guidelines crowded retrieval and pulled the cheap model off-topic.
   The baseline (18) answered it correctly (RESCUEicp/DECRA). This is the spec's predicted
   **dilution** failure mode.

3. **Genuine wins exist but are narrow.** Guidelines clearly helped on neurointerventional
   currency: NIS-01/NIS-02 (**+16** each) reflected current 2025–26 trial/guideline data
   (negative MeVO trials, basilar-occlusion guidance) the textbooks lag on. The opportunity is
   real — but unguarded "dump all 42 into the shared index" trades it for crowding elsewhere.

## Graduation rule (from the design) — result

- guideline-sensitive quality improves → **NOT demonstrated** (cited ≈ uncited; delta n.s.)
- textbook-anchored non-inferior → **FAILED** (TRAUMA-02 −44 crowding; 21 questions regressed)
- citations correct & current → **mixed** (good currency on NIS; misfire on TRAUMA-02)

## Fast-and-cheap read (the cheap stack itself)

| | baseline (18) | treatment (60) |
|---|---|---|
| latency median | 47.2s | **46.5s** (p95 71s vs 87s) |
| answers | safe / B-band (80–89) across the board | same |
| DeepSeek cost | — | **~$0.18 total** for all 134 answers (~$0.0013/answer; measured via balance delta) |
| Vertex disambiguation | 5 calls | 4 calls — negligible |

The cheap stack delivers clinically-safe B-band answers at ~$0.0013 and ~47s each — the
"fast and cheap" goal is met. Guidelines add no latency.

## Recommendation

1. **Keep the guidelines held out of live** (`guidelines_held/`); live index remains 18.
2. **Before any future promotion, gate guidelines behind query-type/domain routing** so they
   surface only on in-domain management/evidence questions — capturing the NIS-type currency
   wins while preventing TRAUMA-02-type crowding. Then re-run this same A/B.
3. The crowding is a **retrieval-layer** issue (off-domain guideline out-ranked the right
   textbook), only partly cheap-model-specific; routing is the fix, not a bigger model alone.

## Reproduce / reverse

- Arms: `evaluation/runs/sandbox-base-cheap-20260630` (18) vs
  `evaluation/runs/sandbox-guidelines-cheap-20260630` (60); per-question
  `ab-comparison.csv`, `ab-verdict.json`, blinded payloads + `keymap.json` under `grading/`.
- Sandbox index `…/index-sandbox` (60) is retained as both the treatment arm and the backup.
- Restore live to 60 (if ever promoting): `rsync` `index-sandbox` back + move PDFs from
  `guidelines_held/`. Live is currently the clean 18-textbook state.
