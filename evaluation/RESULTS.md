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
| clamp-change-20260630 · ref | 2026-06-30 | PubMed neurosurgical domain clamp (ref) | b9a7e37 dirty | 67 | 86.40 | +8.66 | 0/67/0/0 | — | DeepSeek-v4-flash sandbox synth (NOT deploy glm-5.2) — compare ref-vs-change (delta -0.13, ns), NOT vs baseline. Quality wash; clamp arm ~4% faster median. |
| clamp-change-20260630 · change | 2026-06-30 | PubMed neurosurgical domain clamp (change) | b9a7e37 dirty | 67 | 86.27 | +8.53 | 1/66/0/0 | — | DeepSeek-v4-flash sandbox synth (NOT deploy glm-5.2) — compare ref-vs-change (delta -0.13, ns), NOT vs baseline. Quality wash; clamp arm ~4% faster median. |


## Knob-sweep runs — generated + blinded, NOT yet score-logged

Single-variable retrieval/embedder knob arms generated **2026-06-27 on the deploy OpenRouter synth**
(`control` = current defaults). Each arm's 67 answers were produced and a **blinded grading pack was
built** (`evaluation/runs/blinded-grading-2/` — `reranker-set-1.md`, `reranker-set-2.md`,
`embedder-set.md`; key in `blinding-key.json`), but the grades were **never captured into a
machine-readable score**, so there is **no Mean/Δ to log as a table row above**. Recorded here so the
work isn't lost; re-grade the blinded packs to promote any of these to a scored row.

| Arm (run dir) | Knob vs control | Commit | Status |
|---|---|---|---|
| `control-fixed` / `control-bakeoff21` | control: bge-reranker-v2-m3, retrieve_k=40, rerank_k=12, bge-large embed | 9c7ea16 / 06c0b7f | answers only (control) |
| `rerank-none` | **reranker OFF** | f00a9d5 | generated + blinded, ungraded |
| `rerank-qwen3` | **reranker → Qwen3-Reranker-0.6B** | 3a268ea | generated + blinded, ungraded |
| `rerank_k-20-fixed` | **rerank_k 12 → 20** (more reranked context) | 9c7ea16 | generated + blinded, ungraded |
| `retrieve_k-80-fixed` | **retrieve_k 40 → 80** (2× retrieval breadth) | 9c7ea16 | generated + blinded, ungraded |
| `embed-qwen3` | **embedder → Qwen3-Embedding-0.6B** | 3a268ea | generated + blinded, ungraded |

These are the reranker / retrieval-breadth / embedder knobs flagged as the top *unexplored* Ask-quality
levers — they were run and blinded but the A/B grading was not finished into numbers.


## RERANK_K sensitivity — first *graded* knob A/B (20-Q subset, cheap-proxy synth)

Completes one of the ungraded knobs above (`rerank_k`): a single-variable blind A/B — **rerank_k 12
(current default) vs 16** — everything else held constant. **Not a 67-Q score row.** It is a 20-question
subset (`caseboard-ab-sandbox`, human blind-graded 2026-06-30) on a **cheap Vertex `gemini-2.5-flash`
proxy, NOT the deploy `glm-5.2` / `gemini-2.5-pro` synth**, so the means sit on a different scale than
the baseline table above — **do not read a Δ-vs-base**; the only valid comparison is k=12 vs k=16.

| Arm | rerank_k | n | Mean | Head-to-head wins | Latency median | Commit |
|---|---|---|---|---|---|---|
| ref | 12 | 20 | 87.45 | 6 | 39.0s | aad1a0e |
| **change** | **16** | 20 | **88.40** | **14** | 47.9s | aad1a0e |

**Δ (change − ref) = +0.95, paired_t = 2.29** (just past the |t|>2 ≈ p<0.05 line); **head-to-head 14–6
for k=16, 0 ties**. Six regressions, all small (≤3 pts) and **none from retrieval crowding** — graders
read them as co-equal / marginally thinner on one prong, not off-topic dilution from the extra reranked
passages. Cost: k=16 is **~23% slower at the median** (47.9s vs 39.0s; mean 59.4 vs 55.2s; p95 slightly
*lower*, 79.3 vs 88.7).

**Read honestly:** the direction favors k=16, but the effect is **<1 point on 100** and the t-stat sits
**right on the noise boundary at n=20**, measured on a **cheap proxy synth**. Promising, not decisive.
**Do not flip the `RERANK_K` default on this alone** — confirm on the deploy synth and ideally the full
67-Q set first. This promotes the previously "generated + blinded, ungraded" `rerank_k` knob to
**graded → weak-positive, unconfirmed on deploy synth**.


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
| semantic NLI @0.2 (initial) | 0.951 | 0.049 |
| **semantic NLI @0.3 (default since 2026-07-02)** | **0.904** | **0.096** |

(The NLI "unsupported rate" here is just the flag rate = flags/1380; it is *not* the true bad rate.
At 0.3 the gate flags 9.6% of claims to buy fabrication recall — see the recall study below.)

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

**Semantic NLI verifier is the production default (2026-07-02).** `get_default_verifier()` returns
an `NLIVerifier` on `tasksource/deberta-base-long-nli` (long-context doc-NLI cross-encoder; markdown
stripped from both sides), flagging a cited claim when `P(entailment) < 0.3`. The 0.3 threshold is
chosen for **fabrication recall, not precision** — see the recall study below. Design note: strict
SNLI-style models (`cross-encoder/nli-deberta-v3-base`) fail this task entirely — they read
paraphrased clinical claims as "neutral" and flag 40/40; long-context *document*-NLI is what works.

*Terms* (each cited claim is judged by a frontier panel as supported, or **bad** = partial `P` /
not-supported `N`): **flags/1380** = how many of the run's 1380 cited claims the gate marks
needs-verification. **precision** = fraction of flags that are truly bad. **recall** = fraction of
all truly-bad claims the gate catches. **fabrication (N) recall** = recall restricted to the worst
class (`N`, passage doesn't support the claim at all). The aggregate "groundedness" number is just
`1 − flags/1380` — a flag-volume proxy, NOT precision or recall.

**Out-of-sample validation — two-lab judge panel over the verifier's ACTUAL verdicts on the full
pr50 run (2026-07-02).** `evaluation/scripts/judge_verifier.py` built fresh blind gold sets from the
verifier's real verdicts on all 1380 cited claims and had two independent-lab judges
(`anthropic/claude-sonnet-4.5` + `openai/gpt-5.1`, blind and distinct from the answer model glm-5.2
and the deberta checker) label each supported/partial/not. Two sets: (a) a 147-item precision panel
= all 67 flags + an 80-pass stride sample (89% inter-judge agreement,
`evaluation/nli-verifier-oos-validation.jsonl`); (b) a **500-pass recall study** — GPT-5.1 screened
500 passed claims, Sonnet confirmed the positives → consensus missed-bad rate with a Wilson CI
(`evaluation/nli-verifier-recall-study.jsonl`). Total judge cost **$2.17**.

*Threshold sweep* (consensus labels; 567 claims; passes reweighted ×1313/500 to the full run):

| threshold | flags/1380 | precision | overall recall | fabrication (N) recall |
|---|---|---|---|---|
| 0.2 (initial) | 48 (3.5%) | 0.33 | 26% | 43% |
| **0.3 (shipped default)** | **132 (9.6%)** | **0.24** | **52%** | **100%** |
| 0.4 | 298 (22%) | 0.13 | 64% | 100% |

Read this honestly:

- **Recall, not the aggregate metric, is the safety axis — and at the old 0.2 it was too low.** The
  500-pass recall study puts the consensus missed-bad rate at **3.4%, 95% CI [2.1%, 5.4%]** (≈28–71
  of 1313 passes truly bad). Combined with the ~17 the gate catches, **overall recall at 0.2 was
  only ~27% (CI ≈[19%, 38%])**, and it caught just **43% of hard `N` fabrications** — it missed more
  than half of the worst class, including a both-judges-confirmed miss (item 103, GENERAL-03).
- **0.3 is the knee, chosen for fabrication recall.** It catches **100% of the panel's hard `N`
  fabrications** and doubles overall recall (26%→52%), at a modest precision cost (0.33→0.24, whose
  CIs overlap) and ~3× the flag volume (3.5%→9.6% of claims). Past 0.3, precision craters (0.13 at
  0.4) with no `N`-recall gain, so higher buys only noise.
- **Still a screen, not a guarantee.** Even at 0.3 a flag is majority false-alarm (precision ~0.24 —
  *worth-a-look*, not proof) and overall recall is ~52% — a "supported" verdict is a *screen
  passed*, not a proof of grounding.
- **Retraction:** an earlier revision of this note claimed 0.2 gave "flag precision 1.00" and
  well-calibrated groundedness. Both were artifacts of tuning/measuring on the 40-claim in-sample
  set; the out-of-sample numbers above supersede them.
- Cost/footprint: local model (~740MB, first-use download), ~33 ms/claim GPU, ~1.4 s/claim + ~2 GB
  RSS CPU. Opt out with `CASEBOARD_NLI_MODEL=lexical`; retune with `CASEBOARD_NLI_THRESHOLD`.

*Same provenance caveat as above:* LLM-judge panels, not human-expert ground truth — a clinician
spot-check of the confirmed misses would upgrade *strong proxy* to *confirmed*.

---

## Retrieval-breadth sweep — CONCLUDED (2026-07-02)

A dozen breadth/model arms were answered but never graded to a verdict. Concluded here with a
committed paired LLM-judge (`evaluation/scripts/grade_pairs.py`): blinded + order-randomized,
independent judge `anthropic/claude-sonnet-4.5` (distinct from the glm-5.2 answer model), scoring
each answer 0–100. Answers were already on disk (deploy-synth glm-5.2, **bakeoff-21** subset);
control = `control-fixed` (RETRIEVE_K=40 / RERANK_K=12). **Total grading spend: $1.18.** Machine
verdict — the autonomous stand-in for the human blinded sheets, matching the mmr-score-pilot
precedent; a paid human deploy-synth grade is the confirmatory step before calling any flip final.

| Arm | n | mean ctrl | mean arm | Δ (arm−ctrl) | CI95 | t | W/L/T | verdict |
|---|---|---|---|---|---|---|---|---|
| **RERANK_K=20** | 21 | 85.24 | 88.29 | **+3.05** | **[0.89, 5.20]** | 2.77 | 16/5/0 | **DECISIVE → default 12→20** |
| RETRIEVE_K=80 | 20 | 86.35 | 85.00 | −1.35 | [−4.16, 1.46] | −0.94 | 9/11/0 | null/worse → keep 40 |
| rerank-none (RRF only) | 21 | 85.90 | 85.67 | −0.24 | [−4.16, 3.69] | −0.12 | 10/11/0 | null → reranker kept |
| rerank-qwen3 | 21 | 85.29 | 81.86 | −3.43 | [−10.75, 3.89] | −0.92 | 9/12/0 | not > bge → keep bge |
| embed-qwen3 | 21 | 85.33 | 86.76 | +1.43 | [−1.44, 4.30] | 0.98 | 13/8/0 | weak+, CI spans 0 → keep bge-large |

**Only `RERANK_K=20` cleared the decisive bar** (CI95 excludes 0 AND wins>losses) → `neuro_core/config.py`
RERANK_K 12→20. All other defaults unchanged. Full note: `evaluation/runs/graded-breadth/VERDICT.md`.

**Cross-judge confirmation (RERANK_K=20):** the same blinded pairs, re-graded by a second independent
judge (**GPT-5.5**), also favor the arm — Δ +4.71, CI95 [−0.10, 9.53], W/L/T 14/7/0. Convergent with
sonnet-4.5 (Δ +3.05): same direction, overlapping magnitude. GPT-5.5's estimate is larger but noisier
(lower bound at 0, ~p≈0.07 on n=21). Two independent blinded judges agreeing de-risks the flip.

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
