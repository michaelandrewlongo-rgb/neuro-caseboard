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
| fixed (best-sentence precision) | 0.80 | 0.20 |
| **semantic NLI (default since 2026-07-02)** | **0.951** | **0.049** |

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
subset would upgrade this from *strong proxy* to *confirmed*.

**Semantic NLI verifier is the production default (2026-07-02).** `get_default_verifier()` now
returns an `NLIVerifier` on `tasksource/deberta-base-long-nli` (long-context doc-NLI cross-encoder;
flag when `P(entailment) < 0.2`; markdown stripped from both sides). Model and threshold were
selected against the 40-claim gold set via `evaluation/scripts/validate_verifier.py` — but because
the threshold is *tuned* on that set, its in-sample numbers (flag precision 2/2, false-pass 1/38)
are optimistic. The honest evaluation is the **out-of-sample panel** below. Design note: strict
SNLI-style models (`cross-encoder/nli-deberta-v3-base`) fail this task entirely — they read
paraphrased clinical claims as "neutral" and flag 40/40; long-context *document*-NLI is what works.

**Out-of-sample validation — a two-lab judge panel over the verifier's ACTUAL verdicts on the full
pr50 run (2026-07-02).** `evaluation/scripts/judge_verifier.py` built a fresh blind gold set from
the NLI verifier's real verdicts on all 1380 cited claims — every one of its **67 flags** plus an
80-claim stride sample of its passes — and had two independent-lab frontier judges
(`anthropic/claude-sonnet-4.5` + `openai/gpt-5.1`), blind to the verdict and distinct from both the
answer model (glm-5.2) and the checker (deberta), label each supported/partial/not. Judge cost
**$0.95** total. Panel agreement 131/147 = **89%**. Merged labels:
`evaluation/nli-verifier-oos-validation.jsonl`.

| metric (consensus = both judges agree) | NLI (out-of-sample) | lexical (in-sample, 40-Q) |
|---|---|---|
| flag precision | **17/67 = 0.25** (either-judge 0.39) | 2/20 = 0.10 |
| false-pass rate | **3/80 = 0.037** (either-judge 0.125) | 1/20 = 0.05 |
| aggregate groundedness metric | **0.951** (panel-estimated true ≈ 0.95) | 0.80 (floor, true ≈ 0.94) |

Read this honestly:

- **The aggregate metric is now well-calibrated.** Measured 0.951 vs a panel-estimated true rate of
  ≈0.952 (67·0.25 truly-bad flags + 1313·0.037 missed ≈ 66/1380 bad). Unlike the lexical 0.80
  *conservative floor*, 0.951 tracks the real rate — trustworthy as an aggregate quality number and
  a regression tripwire.
- **Flags are 2.5–4× more actionable than lexical** (precision 0.25–0.39 vs 0.10) but still
  majority false-alarm — treat a flag as *worth-a-look*, not proof of a bad claim.
- **It is a low-recall safety screen, NOT a guarantee.** It catches only ≈26% of the ~66
  truly-unsupported claims; it passes real misses, including one **both-judges-confirmed hard "not
  supported"** (item 103, GENERAL-03) and two partials (NIS-05, TUMOR-04). A "supported" verdict is
  a *screen passed*, not a proof of grounding.
- Net vs lexical: better on every measured axis (flag precision, false-pass, metric calibration), so
  it is the better default — but the earlier "flag precision 1.00" claim was in-sample overfitting
  and is retracted here.
- Cost/footprint: local model (~740MB, first-use download), ~33 ms/claim GPU, ~1.4 s/claim + ~2 GB
  RSS CPU. Opt out with `CASEBOARD_NLI_MODEL=lexical`; tune with `CASEBOARD_NLI_THRESHOLD`.

*Same provenance caveat as above:* LLM-judge panel, not human-expert ground truth — a clinician
spot-check of the confirmed false-passes would upgrade *strong proxy* to *confirmed*.

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
