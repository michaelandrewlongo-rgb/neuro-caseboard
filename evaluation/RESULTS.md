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


## Groundedness (citation faithfulness) — a separate metric, not a score row

PR#50 added a computed **groundedness / unsupported-claim-rate** metric (does each cited sentence
follow from the source it cites?). It is **not an answer-quality score and has no row above**: PR#50
is *answer-preserving* (it only attaches verification metadata), so the answers — and therefore the
0–100 grades and Δ — are unchanged. There is nothing to A/B on the score table.

First measurement on the frozen 67-Q set (run `pr50-groundedness-20260622-125141`, textbook `[n]`
lane, 1380 cited claims) exposed a **metric bug**: the default `LexicalVerifier` judged precision
against the *whole* retrieved chunk, so a short well-supported claim (a tiny fraction of a long
passage) was flagged unsupported — an artifact **groundedness 0.07 / ~93% "unsupported"**, not a real
hallucination rate. Fixed on `fix/groundedness-precision-gate` (precision judged against the
best-matching premise *sentence*; off-topic spans still rejected). Re-scored offline on the same run:

| Verifier | groundedness | unsupported rate |
|---|---|---|
| shipped (whole-premise precision) | 0.07 | 0.93 |
| **fixed (best-sentence precision)** | **0.80** | **0.20** |

Per-domain (fixed): Neurointerventional 0.86 · Open-CV 0.82 · Spine 0.80 · Functional 0.80 ·
General 0.78 · Trauma 0.79 · Tumor 0.73. This is a conservative *lexical* proxy (it flags paraphrase
and cross-chunk synthesis), so read it as a relative signal, not an absolute hallucination rate. The
`[L#]` literature lane isn't re-scored offline (its abstracts aren't stored in the run record).

**Validated by an independent frontier-model judge (2026-06-22) — not a human expert** — against a
40-claim blind gold set (`evaluation/groundedness-gold-set.jsonl`): a separate frontier LLM (distinct
from the answer-generating model *and* from the checker) graded 20 checker-passed + 20 checker-flagged
claims supported/partial/not, blind to the checker's verdict, with per-item entailment reasoning.
Result — the checker is **high-precision, low-recall about problems**: when it says **supported it is
right 95%** (19/20; dangerous false-pass rate **5%**, the one miss a partial not a fabrication — it
caught the only true hallucination and the knowledge-injection case), but when it **flags, ~90% are
false alarms** (18/20 were actually supported). So the **judge-estimated true groundedness is ≈0.94**,
and **the 0.80 headline is a conservative floor** (over-flagging drags it down), not the real rate.
**Use 0.80 as a safety screen and regression tripwire — trust a "supported" verdict, treat a "flag"
as worth-a-look — not as an absolute quality number.**

*Provenance caveat:* this is an **LLM-judge** validation, not human-expert ground truth. The judge is
independent, semantic, and blinded (a strong proxy), but it can share blind spots with LLM-generated
answers, so "agreement with the judge" is not "agreement with truth." A clinician spot-check of a
subset would upgrade this from *strong proxy* to *confirmed*. To de-noise the flags, swap in the
semantic NLI verifier (`CASEBOARD_NLI_MODEL`) and validate it against the saved gold set.

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
