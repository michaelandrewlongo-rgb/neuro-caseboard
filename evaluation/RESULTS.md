# 67-Question Benchmark — Run Results

One row per full run of the frozen 67-question neurosurgery benchmark. The **baseline** row is the
reference point; every other row shows what changed and how the score moved.

**How to read it:** **Mean** is the average answer score from 0–100 (higher is better). **Δ vs
base** is this run's mean minus the baseline's — positive means better than baseline. **Unsafe** is
the count of answers a grader flagged as unsafe; this must stay **0**. **A/B/C/D** is how many
answers earned each letter grade. Small mean differences (±2–3) are usually run-to-run noise, not a
real change.

**How it's updated:** after a full run, `evaluation/scripts/update_results.py` adds or refreshes
that run's row from its score files (see the command at the bottom). Do not hand-edit rows.

| Run | Date | Change | Commit | n | Mean | Δ vs base | A/B/C/D | Unsafe | Notes |
|---|---|---|---|---|---|---|---|---|---|
| baseline-20260620-134705 | 2026-06-20 | baseline | 28a6e30 dirty | 66 | 77.74 | — | 0/38/22/6 | 0 | 1 not-gradable |
| post-improvement-20260620-182930 | 2026-06-20 | C5 empty-answer guard | eb9e981 dirty | 66 | 79.36 | +1.62 | 0/44/19/3 | 0 | delta within run-to-run noise |
| youmans-full67-20260620-2210 · recent | 2026-06-20 | 3-arm corpus A/B (recent) | 9f5138a dirty | 67 | 78.66 | +0.92 | 0/44/22/0 | — | length confound on composed arm |
| youmans-full67-20260620-2210 · youmans | 2026-06-20 | 3-arm corpus A/B (youmans) | 9f5138a dirty | 67 | 80.03 | +2.29 | 0/55/11/0 | — | length confound on composed arm |
| youmans-full67-20260620-2210 · youmans_pubmed | 2026-06-20 | 3-arm corpus A/B (youmans_pubmed) | 9f5138a dirty | 67 | 83.87 | +6.13 | 0/61/5/0 | — | length confound on composed arm |

## Isolated-grader experiments (Phase 0B / 1-D)

> **Different grader — NOT comparable to the table above.** These runs grade each answer **in
> isolation** (one answer → 0–100) to remove the joint/contrast confound of the 3-arm benchmark.
> The isolated grader is harsher and more variable, so absolute means (~84–86) do **not** line up
> with the joint-graded rows — read the **paired Δ vs each experiment's own control**, not the
> absolute mean. Single self-grader (vertex/gemini-2.5-pro); directional. Source summaries:
> `eval/placebo/`, `eval/mmr-score/`, `eval/mmr-score-007/`.

**Phase 0B — PubMed lane de-confound** (isolated grading, n=64; control = `core`)

| Arm | n | Mean | Paired Δ vs core | Read |
|---|---|---|---|---|
| core (youmans, no appendix) | 64 | 86.16 | — | control |
| real (+ real PubMed appendix) | 64 | 86.11 | −0.05 | appendix is score-neutral → the +3.9 was a joint-grading artifact |
| placebo (+ length-matched boilerplate) | 64 | 80.59 | −5.56 | padding *hurts* → not a length effect |
| scramble (+ wrong-topic real appendix) | 64 | 61.25 | −24.91 | off-topic content is catastrophic → relevance gating matters |

**Phase 1-D — MMR diversity score effect** (isolated grading, paired off vs on)

| Run | n | Mean off | Mean on | Paired Δ (on−off) | 95% CI | W/L/T |
|---|---|---|---|---|---|---|
| MMR on @0.07 | 62 | 83.56 | 84.81 | +1.24 | [−1.21, +3.69] | 26/26/10 |
| MMR on @0.15 | 59 | 85.61 | 85.80 | +0.19 | [−2.48, +2.85] | 18/23/18 |

**Phase 1-D — MMR Δ (on−off) by subspecialty**

| Subspecialty | Δ@0.07 | Δ@0.15 |
|---|---|---|
| Neurointerventional | +9.9 | +8.9 |
| Spine | +4.4 | −3.3 |
| Brain Tumor | +3.1 | +4.9 |
| Open Cerebrovascular | +1.2 | +1.0 |
| General | −1.1 | +0.9 |
| Functional | −2.6 | −5.3 |
| Trauma | −3.9 | −4.8 |
| **Overall** | **+1.24** | **+0.19** |

Takeaway: the +3.9 "PubMed gain" is a joint-grading artifact (real appendix is score-neutral in
isolation); MMR helps the specialized fields Youmans crowds out (NIS/Tumor/Spine) but a flat global
penalty is only mildly net-positive — recommend default `RERANK_MMR_BOOK_PENALTY=0.0`, 0.07 if
enabling, with a subspecialty-conditional penalty as the real fix.


---

Update a row after a full run:

```bash
# single-arm run (canonical *-summary.json):
python3 evaluation/scripts/update_results.py \
    --summary evaluation/runs/<run>/<prefix>-summary.json \
    --run <run-dir-name> --label "<what changed>"   # add --baseline for the anchor row

# A/B run (one row per arm, read from grading/keymap.json + ab-out/<arm>-grades.jsonl):
python3 evaluation/scripts/update_results.py --ab evaluation/runs/<run> --label "<what changed>"
```
