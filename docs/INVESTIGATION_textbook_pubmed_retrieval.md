# Investigation: Optimal Textbook + PubMed Retrieval Strategy

**Repo:** `neuro-caseboard` (master) • **Benchmark:** `youmans-full67-20260620-2210` (67 Qs, blinded, 3 arms)
**Status:** investigation + Phase-0A/1-C implementation landed (working tree, uncommitted). Findings labeled **VERIFIED** (traced to code / computed from data) vs **HYPOTHESIS / INFERRED**. See **"Phase 0A Results"** and **"Implementation Status"** at the end.

---

## 0. TL;DR

The headline numbers conflate two *independent* systems with *different* failure modes:

| Arm | Score | What it actually is |
|---|---|---|
| recent (baseline) | 78.7 | textbook hybrid retrieval, single flat pool |
| + Youmans wholesale | 80.0 (+1.4) | **same pool, +1 book** → structural crowd-out |
| + PubMed concatenated | 83.9 (+5.2) | **a separate appended lane** → length-confounded |

1. **Youmans regressions (27/67) are real and structural.** Textbook retrieval is one flat ranked pool capped at top-40 → top-12 with **no per-book quota, no score threshold, no token budget**. Adding Youmans evicts other books' passages purely by rank. corr(baseline, Δ) = **−0.826**; *every* question with baseline ≥85 regressed (−5.6 mean). **VERIFIED.**
2. **The PubMed lane is already separate, not merged.** It is LLM-*synthesized* (not raw-concatenated), then *appended* as a "Contemporary Literature" section. The core textbook answer is byte-identical between the youmans and youmans_pubmed arms. **VERIFIED.**
3. **The +3.9 PubMed gain is a bolt-on appendix effect, confounded with a 72% length increase.** Two questions where the appendix wasn't generated show exactly 0 gain. Length explains ~18% of variance; the gain is suspiciously *uniform* (+3 to +4 regardless of content), suggesting the grader rewards the *presence* of a literature section. **VERIFIED / INFERRED.**
4. **PubMed's own 12 regressions are inherited from Youmans crowd-out**, not caused by off-topic citations — 11/12 already regressed in the youmans arm; the appendix only partially recovered them. Inspected regressions had *on-topic* literature. **VERIFIED / INFERRED.**
5. **Off-topic PubMed citations are nonetheless a latent risk**: citations enumerate *everything retrieved*, not everything *used* (`qa.py:94`), and the only relevance gate is PubMed's own `sort=relevance` plus a publication-type floor that a single-article fallback defeats. The benchmark didn't surface this as a score driver, but the leak path is real. **VERIFIED.**

**Implication:** the textbook crowd-out and the PubMed lane are two separate problems. Fix crowd-out at the *retrieval* layer; de-confound PubMed at the *evaluation* layer before trusting its gain.

---

## 1. Current architecture (VERIFIED)

### 1a. Textbook lane (`neuro_core/`)
```
query() query.py:260
 → Engine._retrieve() query.py:172
     → embed_query() embed.py:26                     # BGE, L2-normalized
     → Index.hybrid_search() index.py:116            # one flat pool
         → vector_search() index.py:108              # LanceDB ANN over chunks.vector
         → text_search()   index.py:112              # LanceDB FTS / BM25 over chunks.text
         → reciprocal_rank_fusion() index.py:22      # RRF k=60, rank-based, NOT score-normalized
     → Reranker.rerank() rerank.py:18                # cross-encoder bge-reranker-v2-m3, overwrites score
 → synthesize() synthesize.py:88
     → _format_passages() synthesize.py:49           # number [1..N] in reranked order, concatenate all
```
- **Corpus = textbooks.** Single LanceDB table `chunks`; each row has a `book` column. "Youmans" is just one value — **no book-specific code anywhere** (`grep youmans neuro_core/` = 0 hits).
- **Cutoffs:** `RETRIEVE_K=40` (`config.py:22`) → `RERANK_K=12` (`config.py:23`). These are the only knobs governing how many passages survive.
- **Dedup:** by chunk `id` during RRF only (`index.py:119`). No `(book,page)` dedup.
- Separate **figure/visual lanes** exist (`query.py:71-95`, capped `MAX_FIGURE_IMAGES=5`) — modality lanes, not source lanes.

### 1b. PubMed / literature lane (`neuro_caseboard/literature/`)
```
answer_question() qa.py:103                           # runs Lane A + Lane B concurrently
 → build_literature_section() qa.py:41
     → rewrite_pubmed_query() retriever.py:66         # LLM query rewrite (fallback: token dump :41)
     → PubMedClient.search() pubmed_client.py:96      # esearch sort=relevance, retmax=40
       (5-axis fan-out: plain + systematic_review/etiology/diagnosis/prognosis retriever.py:140)
     → esummary/efetch hydrate abstracts pubmed_client.py:108/135/171
     → rank_key() retriever.py:166                    # relevance bucket (//5) → pub_tier → recency → year
     → standardize_records() standardize.py:15        # pub-type floor tier≤2; single-article fallback :23
     → synthesize_literature() synth.py:44            # LLM synthesis → flowing prose w/ [L#]; refusal→None
 → QAResult(answer=LaneA, literature=LaneB)           # SEPARATE FIELDS — never merged qa.py:114
 → render_md.py:60-71                                 # append "Contemporary Literature" section verbatim
```
- **The two lanes never reconcile.** Lane A (textbook `[n]`) and Lane B (PubMed `[L#]`) are disjoint citation spaces by design (`case_literature.py:6`, `compile.py:88`).
- **Config:** `LITERATURE_RETRIEVAL` (on), `LITERATURE_K=12`, `LITERATURE_RECENCY_YEARS=7` (`literature/config.py:77-79`). Fan-out f 5 axes and `candidates=40` are hardcoded.
- `neuro_core/live_reconcile.py` is **legacy/dead** (zero live callers).

### 1c. Capability checklist (what exists today)

| Capability | Textbook lane | PubMed lane |
|---|---|---|
| Independent per-source lanes | ❌ flat pool (per-*modality* only) | ✅ separate lane |
| Question-type routing | ❌ | ❌ (always runs if enabled; case path routes by *section heading* only) |
| Per-lane relevance threshold | ❌ no score floor | ❌ no topical/semantic gate (only PubMed `sort` + pub-type floor) |
| Source quota / token budget | ❌ none (`config.py:18` "no token cap") | ❌ no narrative cap; only input `k=12` |
| Deduplication | ✅ by chunk id | within-lane only; ❌ cross-lane |
| Evidence-quality weighting | ❌ | ⚠️ pub-type tier ordering only (`pub_tier`), defeated by fallback |
| Abstention | ❌ | ✅ LLM refusal + empty-result drop (`synth.py:17`, `qa.py:89`) |
| Synthesis vs concatenation | n/a single lane | ✅ within-lane LLM synthesis, but ❌ appended, not reconciled with textbook |
| Cite-what-you-use | ✅ `[n]` gated by `should_cite` entailment (`compile.py:155`) | ❌ `[L#]` enumerates *all retrieved* records (`qa.py:94`) — leak path |

---

## 2. Likely failure mechanisms

### F1 — Textbook crowd-out (VERIFIED, structural, high confidence)
A fixed top-12 slice over a book-agnostic ranked pool (`rerank.py:25`) has **no reserved slots**. Any Youmans chunk scoring above an incumbent evicts the incumbent. Confirmed by data: corr(baseline,Δ)=−0.826; 9/9 of ≥85-baseline questions regressed under youmans (−5.56 mean). The wholesale-add helps weak topics (FUNCTIONAL +5.7, baseline <75 +9.7) precisely because it displaces — which is fine when the displaced passage was weak and harmful when it was strong.

### F2 — PubMed gain is length/section-presence confounded (VERIFIED methodological)
The youmans_pubmed *core* body == youmans body (Δ<0.3 chars mean). The +3.89 is entirely the ~3,089-char appended lane. Won 61/66 but with a **uniform** +3–4 magnitude uncorrelated with lane content (corr=+0.42, R²≈0.18) → grader likely rewards *having* a contemporary-literature section. The 2 questions with no generated lane show gap = 0. **The gain is real text but its *cause* (evidence quality vs length/format) is unproven.**

### F3 — PubMed off-topic citation leak (VERIFIED latent, not yet a score driver)
Citations list = all `syn.records` (everything retrieved), not what the narrative cited. The only gates between PubMed and the citation list are NCBI's `sort=relevance` + a pub-type floor whose single-article fallback (`standardize.py:23`) admits a low-tier article when nothing qualifies. An on-topic-but-tangential or single-fallback study appears as a citation regardless of use. Benchmark didn't show this driving regressions, but it will surface on narrow/rare-topic questions.

### F4 — No routing / no abstention on the textbook side (VERIFIED)
Nothing decides a question is "already strong, add nothing." Every question gets the full top-12 textbook pool and (if enabled) the full PubMed fan-out. Strong questions have the most to lose and the least to gain — exactly where regressions concentrate.

---

## 3. Recommended architecture

**Dual independent lanes with reserved budgets, per-lane relevance gates, confidence-gated inclusion, and cite-what-you-use.** This keeps the PubMed gain, removes the textbook crowd-out, and closes the citation leak — without a risky rewrite (the lanes are *already* separate; the work is mostly gating).

1. **Protect the textbook lane from crowd-out (fixes F1 — highest value).**
   - Add a **per-book / per-source reservation** OR a **relevance-floor + dynamic-K**: keep a passage only if its cross-encoder score ≥ `RERANK_MIN_SCORE`, and reserve ≥`MIN_SLOTS_PER_BOOK` for incumbent books so a new book cannot evict all of them. Start with a score floor (smaller change) and measure.
   - Rationale: the eviction is purely rank-based with no floor (`rerank.py:25`); a floor converts "always 12" into "the 12 that clear the bar," so a marginal Youmans chunk no longer displaces a strong incumbent.

2. **Confidence-gated literature inclusion (fixes F2/F4).**
   - Compute a cheap **answer-confidence / topic-novelty signal** (e.g., top textbook rerank score, or whether retrieval already covers the question). Only attach the PubMed lane when the textbook answer is weak or the question is time-sensitive. This stops appending 3k chars of literature to already-strong questions (where it adds length, not value, and risks F3).

3. **Per-lane topical relevance gate for PubMed (fixes F3).**
   - Insert a **semantic rerank** (reuse the existing cross-encoder) between `standardize_records` and `synthesize_literature`: score each abstract against the question, drop below `LIT_MIN_SCORE`. Remove or tighten the single-article fallback.

4. **Cite-what-you-use for `[L#]` (fixes F3 leak).**
   - Reconcile the rendered citation list against the `[L#]` markers actually emitted by the synthesizer (mirror the `should_cite` entailment gate already used for `[n]` at `compile.py:155`). Drop uncited records from the list.

5. **Synthesis that reconciles, not appends (optional, addresses F2 properly).**
   - Replace the appended section with a **single reconciliation pass** that merges textbook + literature into one answer, flagging where literature *updates* the textbook. This removes the length confound (one answer, not answer+appendix) and lets the model say "literature concurs/contradicts." Higher risk → gate behind the eval matrix below.

---

## 4. Alternative architectures (tradeoffs)

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. Dual retrieval + late fusion** (recommended core) | Separate textbook & PubMed retrieval, fuse with per-lane budgets + floors | Minimal change (lanes already separate); directly fixes crowd-out & leak; preserves gain | Doesn't reconcile contradictions; appendix length confound remains unless combined with #5 |
| **B. Adaptive source routing** | Classify question (anatomy/technique/evidence/recent) → choose lanes/weights | Stops wasting PubMed on pure-fact Qs; reduces F3 exposure | Needs a reliable classifier; routing errors silently drop a useful lane |
| **C. Textbook-first + PubMed updating** | Textbook is the spine; PubMed only injected where it *changes* guidance | Matches clinical reasoning; literature earns its place | Requires contradiction detection; more LLM calls |
| **D. PubMed-first + textbook grounding** | Lead with current evidence, ground definitions in textbook | Best for fast-moving topics | Inverts a system whose strength is the curated corpus; risky on stable anatomy Qs |
| **E. Confidence-gated inclusion** | Attach a lane only when answer confidence low / topic time-sensitive | Cheap; directly removes "append to already-strong" failure | Confidence signal must be calibrated or you suppress useful evidence |

**Recommendation:** ship **A + E** first (cheap, fixes the two verified mechanisms), evaluate, then consider **C** for the reconciliation upside. B/D are larger bets to defer.

---

## 5. Proposed evaluation matrix

The current 3-arm benchmark cannot separate evidence quality from length. Add these arms on the **same 67 questions** (+ a held-out set to avoid overfitting):

| # | Arm | Isolates |
|---|---|---|
| 1 | recent (baseline) | control |
| 2 | youmans wholesale | crowd-out magnitude (current) |
| 3 | youmans + score-floor / reserved-slots | **does the floor remove F1 regressions?** |
| 4 | youmans_pubmed (append) | current PubMed effect (length-confounded) |
| 5 | youmans_pubmed **length-matched placebo** (append a same-length *irrelevant* or generic-boilerplate section) | **is the grader rewarding length/section presence?** (F2) |
| 6 | youmans + PubMed **reconciled into one answer** (no appendix) | PubMed value with length controlled |
| 7 | youmans + PubMed with **topical rerank + cite-what-you-use** | F3 fix — does precision change score / citation count? |
| 8 | confidence-gated (attach PubMed only when textbook weak) | F4 — gain retained with fewer attachments? |

**Primary metrics:** blinded pairwise win-rate AND absolute score; **regression count vs baseline** (not just mean — the mean hid 27 regressions); per-subspecialty Δ; baseline-strength-bucketed Δ. **Confound controls:** answer char length per arm, #citations per arm, and a length-residualized score (regress score on length, compare arms on the residual). Arm 5 is the critical placebo — if arm 5 ≈ arm 4, the PubMed "gain" is largely format/length.

---

## 6. Instrumentation needed (before/with implementation)

Verified gaps in current logging:
- **Per-passage provenance in the answer:** log, per question/arm, every retrieved textbook chunk with `book`, `rerank_score`, and whether it survived to top-12 and whether it was *cited*. (Today `textbook_citations.csv` exists but not the *displaced* set.) → needed to measure crowd-out directly.
- **Displacement diff:** for the youmans arm, log which baseline chunks fell out of top-40/top-12 when Youmans was added. This makes F1 observable per question.
- **PubMed retrieved-vs-cited:** log each `syn.record` with its `pub_tier`, PubMed relevance rank, a topical-similarity score (once the rerank exists), and whether the narrative actually emitted its `[L#]`. → quantifies F3 leak.
- **Lane-attached flag + lane length** per question (the analysis had to reverse-engineer this from text). Emit `literature_attached: bool`, `lane_chars`, `core_chars`.
- **Confidence signal:** log top textbook rerank score per question (proxy for "already strong") so routing/gating can be calibrated against the baseline-strength pattern.
- **Grader length controls:** record answer length and citation count alongside every grade so length-residualized analysis is one query, not a forensic reconstruction.

---

## 7. Implementation tickets (ordered by expected value)

> Value = (benchmark evidence it addresses a real, large effect) × (low risk / small change). No code changed yet; each ticket is a proposal.

| # | Ticket | Addresses | Effort | Expected value | Risk |
|---|---|---|---|---|---|
| **T1** | **Add `RERANK_MIN_SCORE` floor + dynamic K** to `rerank.py:25` (keep top-12 *that clear the bar*) | F1 crowd-out | S | **High** — directly attacks the −0.826 baseline-correlated regressions; cheapest lever | Low (config-gated, default off) |
| **T2** | **Crowd-out / displacement instrumentation** (per-passage provenance + displaced-set log) | observe F1, validate T1 | S | High — without it T1/T3 are flying blind | Low |
| **T3** | **Per-book reserved slots** in the top-12 (`MIN_SLOTS_PER_BOOK`) | F1 (stronger than T1 alone) | M | High — prevents one book monopolizing context | Med (tune so weak-topic gains survive) |
| **T4** | **Length-placebo + length-residualized eval arms** (matrix arms 5, 6) | F2 confound | S | **High** — tells you whether the +3.9 PubMed gain is real before investing in PubMed at all | Low (eval only) |
| **T5** | **Cite-what-you-use for `[L#]`** — reconcile citation list against emitted markers (mirror `compile.py:155`) | F3 leak | S | Med-High — closes the off-topic-citation path; cheap correctness win | Low |
| **T6** | **PubMed topical rerank gate** (cross-encoder between `standardize_records` and synth; drop low-score; remove single-article fallback) | F3 | M | Med — precision win; benchmark didn't show it as a score driver yet, so pair with T4/instrumentation | Low-Med |
| **T7** | **Confidence-gated literature inclusion** (attach PubMed only when textbook weak / topic time-sensitive) | F2/F4 | M | Med — stops appending to strong answers; depends on a calibrated confidence signal (instrument first) | Med |
| **T8** | **Reconciled single-answer synthesis** (merge lanes, flag literature *updates*) | F2 root cause | L | Med (high upside, high uncertainty) — only after T4 proves PubMed adds evidence, not length | High |
| **T9** | **Adaptive source routing** (question-type classifier) | F4 | L | Deferred — larger bet; revisit after T1–T7 | High |

**Suggested first sprint:** T2 → T1 → T4 → T5 (all Small, all directly target a verified mechanism), then evaluate before committing to T3/T6/T7.

---

## Appendix — key data points (computed, gradable n=66)

- Aggregates reproduced: recent 79.85 / youmans 81.24 / youmans_pubmed 85.14 (all-67 incl. ungradable SPINE-02=0 → 78.66/80.03/83.87, matching reported 78.7/80.0/83.9).
- youmans: 27 regressed / 35 improved / 4 tied; corr(baseline,Δ)=−0.826; ≥85 bucket: 9/9 regressed, −5.56 mean.
- youmans_pubmed: 12 regressed / 54 improved; 11/12 inherited from youmans regression; corr(baseline,Δ)=−0.883.
- Subspecialty: youmans **regresses** NIS −1.25, OPEN-CV −0.50, SPINE −1.75 (highest-baseline/procedural); gains FUNCTIONAL +5.70, GENERAL +2.82. youmans_pubmed net-positive everywhere.
- Length: core body youmans==youmans_pubmed (Δ<0.3 char); appendix ≈3,089 chars (+72%); paired gap +3.89 (61/66 wins, p≈8e-19) but 0 when appendix absent; corr(lane length, gap)=+0.42 (R²≈0.18).
- Off-topic-PubMed regression: none found in inspected cases (OPEN-CV-03, SPINE-08 were on-topic).

*Trace evidence: `neuro_core/{query,index,rerank,synthesize,config}.py`; `neuro_caseboard/{qa,render_md,case_literature,compile}.py`, `neuro_caseboard/literature/{retriever,pubmed_client,synth,standardize,config}.py`. Data: `evaluation/runs/youmans-full67-20260620-2210/`.*

---

# Council Review & Revised Course of Action

A four-expert council (IR/retrieval architect, evaluation methodologist/biostatistician, academic neurosurgeon/EBM, pragmatic staff engineer) reviewed the above. They **corrected two claims** in the original report and converged on a tighter plan. The revised plan below **supersedes §7's ticket ordering.**

## Corrections to the original report (council, high confidence)

1. **"F1 crowd-out is VERIFIED structural" was an OVERCLAIM — downgrade to HYPOTHESIS pending logs.** The −0.826 baseline×Δ correlation is largely **regression-to-the-mean** (correlating a bounded, quantized baseline against post−baseline mechanically yields a negative slope). Decisive evidence: the *appended* PubMed arm — which by construction **cannot** evict textbook passages — shows an even **stronger −0.883**. Same statistical artifact, zero eviction possible. Crowd-out may be real, but it must be proven from **retrieval displacement logs**, not the score correlation. (methodologist + IR architect, independently)
2. **The "+1.4 Youmans effect" is statistically indistinguishable from zero** — 95% CI [−0.02, +2.81], t≈1.97, p≈0.05. Treat as a null; do not make decisions on it. (methodologist)
3. **Drop the "length explains ~18% of variance (R²≈0.18)" framing** — it *undercuts* the length argument (R² on residuals says nothing about whether the mean +3.9 shift is format-driven). The real evidence for the length/format confound is the two strong points the report already has: **0 gain when the appendix is absent**, and a **near-degenerate +2–5 delta distribution** (a real evidence intervention produces heterogeneous effects; a uniform tier-bump signals format reward). (methodologist)
4. **A second, under-attributed crowd-out point exists:** the **recall gate** (top-40 candidate pool in `hybrid_search`, `index.py:116`), not just the selection gate (top-12). A strong incumbent can fall out of the 40 *before the cross-encoder ever sees it* — no rerank floor can rescue it. Fix: widen `RETRIEVE_K` (40→60/80). (IR architect)

## Points of consensus (all four experts)

- **Instrument displacement FIRST (was T2). It needs no grader** — it measures eviction directly and settles the crowd-out question that the score correlation cannot. Unanimous #1.
- **Run a placebo eval BEFORE writing any PubMed-quality code.** Do not build T6/T7/T8 on a possibly-phantom signal. Unanimous.
- **"Cite only what you used" (was T5) is a cheap correctness win and ships freely** — it is never wrong to drop an uncited reference. The clinician elevates it to a **safety/medico-legal invariant** (a fabricated/uncited citation in surgical prep misleads trainees and reads badly in discovery).
- **Cut/shelve the heavy items: T8 (reconciled synthesis) and T9 (adaptive routing)** — high-risk one-way doors, deferred by the report itself, unjustified on an n=67 noisy benchmark.

## Points of contention (surfaced, not buried)

- **Raw score floor (old T1):** IR architect calls it the **worst** retrieval option — bge-reranker logits are uncalibrated and shift per query, so a global constant over-prunes hard queries and under-prunes easy ones. Prefer **query-relative dynamic-K + MMR diversity** (keep passages within a ratio of the top score; soft same-book redundancy penalty). The pragmatist still likes a flag-gated floor as the *cheapest* first cut. **Resolution:** ship the relative/dynamic-K + MMR version, not a raw constant; if time-boxed, a flagged floor is an acceptable v0 *only* with the displacement logs to tune it.
- **Per-book reserved slots (old T3):** IR architect says **anti-pattern** (books aren't the relevance unit; hard quotas kill the weak-topic Youmans gains). Clinician says source authority **is** subspecialty-specific (Youmans is strong for open-vascular anatomy, dated for neurointervention/degenerative spine) and wants per-(book×subspecialty) trust. **Resolution:** achieve diversity via **MMR (relevance-based)**, not hard quotas; treat subspecialty-trust weighting as a *later* experiment, not a first move.
- **Question-type routing (old T9):** clinician considers it clinically essential (textbook authoritative for stable anatomy; PubMed must override on thrombectomy windows, flow diverters, 2021 WHO glioma reclassification, DBS). Methodologist/pragmatist say defer (classifier risk on n=67). **Resolution:** clinically right long-term, but **not** the first move — earn it after the cheap wins and better eval.
- **Single-article low-tier fallback (`standardize.py:23`):** clinician calls it **clinically unacceptable** — when nothing clears the evidence bar the system should **abstain**, not admit a case report as the basis for surgical guidance. Kill the fallback; make recency **field-weighted** (a landmark RCT must outrank a recent case series; a flat 7-yr window buries ISAT/STICH/the thrombectomy trials).

## Revised course of action (council consensus)

**Phase 0 — Measure (no production code; grader-independent where possible):**
- **A. Displacement instrumentation** at BOTH the top-40 recall gate and top-12 selection gate, with/without Youmans. Settles real-eviction vs regression-to-mean. *No grader needed.*
- **B. PubMed de-confound eval:** arms = real appendix / **length-matched boilerplate placebo** / **content-scrambled real citations** (right format, wrong question), graded **in isolation** (not jointly), ideally with a **second / non-Gemini grader** and an ICC. If all three arms score alike, the +3.9 is pure format — stop the PubMed-quality workstream.

**Phase 1 — Cheap, reversible, ship behind flags:**
- **C. Cite-what-you-use** for `[L#]` (reconcile rendered citations against emitted markers; mirror `compile.py:155`) **+ kill the single-article fallback** (abstain instead). Correctness + safety invariant.
- **D. Retrieval fix:** **query-relative dynamic-K + MMR diversity** and **widen `RETRIEVE_K`** — *not* a raw score floor, *not* per-book quotas. Flag-gated, tuned against the Phase-0A logs.

**Decision under uncertainty (pragmatist, endorsed by the council):** **Ship C + D behind flags now; keep all PubMed-quality work (rerank/gating/synthesis) eval-only until Phase-0B clears the placebo.** The literature *appendix* has user value and can stay as a feature; do not *trust its score* or build on it until de-confounded. **Don't pause** — the crowd-out fix and citation fix are ready and correct.

**Deferred until eval demands:** PubMed topical rerank, confidence-gated inclusion, per-(book×subspecialty) trust. **Shelved:** reconciled single-answer synthesis, adaptive question-type routing.

*Estimated effort for Phase 0 + Phase 1: ~2–3 focused days, captures the verified win + the citation/safety fix + the data to justify or kill everything else.*

---

# Phase 0A Results — Crowd-out, measured grader-independently

Run: `scripts/retrieval_displacement.py` over all 67 benchmark questions against the live
index (Youmans = ~72% of corpus chunks by volume), capturing the full ranked ordering at
both gates and computing the counterfactual "what does Youmans evict" by post-hoc removal
of Youmans from the ordering (no reindex). **No grader, no LLM — pure retrieval logs.**
Artifacts: `eval/displacement-selection/`, `eval/displacement-recall/`.

| Metric | Selection gate (top-12, answer-affecting) | Recall gate (top-40 pool) |
|---|---|---|
| Questions where Youmans takes ≥1 slot | **65 / 67** | 67 / 67 |
| Questions with ≥1 evicted passage | **64 / 67** | 67 / 67 |
| Total passages evicted | 352 | 1,157 (lower bound¹) |
| Mean evicted / question | **5.25 / 12 (≈44% of context)** | 17.3 / 40 |
| Mean marginal gap² | **0.040** | 0.0007 |

¹ recall pool captured to depth 120; passages pushed beyond 120 are not counted.
² marginal gap = score of the weakest Youmans chunk that kept a slot − score of the
strongest passage it evicted. Near-zero ⇒ the cross-encoder is essentially indifferent
between what it keeps and what it drops.

## What is now VERIFIED (this resolves the council's F1 correction)

1. **Crowd-out is real eviction, not a regression-to-the-mean artifact.** The −0.826 score
   correlation the council (correctly) flagged as RTM is *not* what this rests on — this is
   measured directly from retrieval logs. Youmans evicts non-Youmans passages on **64/67**
   questions; on the answer-affecting top-12 gate it displaces **~44% of the context** on
   average. The "is the crowd-out even real?" question is settled: **yes, mechanistically.**
2. **The eviction is marginal.** Selection-gate mean gap **0.040**; **45/64** questions evict
   at gap < 0.05 and **16/64** at gap < 0.01 (cross-encoder scores essentially tied). At the
   recall gate the gap is **0.0007** — statistically indistinguishable scores. Combined with
   Youmans being ~72% of the corpus, Youmans wins ~44% of slots by **volume + razor-thin
   margins**, not by being decisively more relevant. So on ~half the slots the selection is
   near-arbitrary — exactly the fragility a relevance-relative cut + MMR diversity would fix.

## The honest nuance (bounds the claim — HYPOTHESIS, not VERIFIED)

**Displacement count does not by itself predict whether a question gains or regresses.**
- Weak-baseline *gainers* also have heavy displacement (FUNCTIONAL-04: 7 evicted; FUNCTIONAL-01:
  5 evicted) — here Youmans displacing weaker incumbents *helps*.
- **NIS-02 regressed in the benchmark (−3) with ZERO selection-gate displacement** (0 Youmans
  chunks in its top-12). Its regression cannot be a top-12 crowd-out effect at all — it points
  to recall-gate effects, synthesis-level effects, or noise (NIS n=8 deltas are within the
  methodologist's noise band).

So displacement is the **mechanism that makes retrieval fragile** (near-arbitrary on ~44% of
slots); whether a given eviction *helps or hurts* depends on whether the displaced passage was
better than the Youmans chunk — which counts cannot see. That valence still needs a
content-level / grader eval (Phase 0B). **What 0A proves: the fix should stabilize *which*
passages survive (dynamic-K + MMR), not assume "more Youmans = worse."**

## Worked examples (selection gate)

| qid | bench Δ (youmans) | Youmans in top-12 | evicted | marginal gap |
|---|---|---|---|---|
| OPEN-CV-03 | −9 | 6 | 6 | **0.009** (near-tied eviction on a strong-baseline Q) |
| TRAUMA-09 | −6 | 5 | 5 | **0.007** |
| GENERAL-01 | −10 | 8 | 7 | 0.022 |
| SPINE-08 | −6 | 9 | 9 | 0.050 |
| NIS-02 | −3 | **0** | 0 | n/a (regression unexplained by selection crowd-out) |
| FUNCTIONAL-04 | **+20** (gainer) | 11 | 7 | 0.050 |

The strong-baseline regressors (OPEN-CV-03, TRAUMA-09) evict at the *tightest* gaps — Youmans
barely out-scores specialized passages it pushes out, consistent with "displaced a nearly-as-good
specialized source." The gainer (FUNCTIONAL-04) shows the same machinery helping. Same mechanism,
opposite valence — which is the whole argument for diversity-aware selection over a flat top-K.

---

# Implementation Status (working tree, `master`, uncommitted)

| Item | Status | Files | Tests |
|---|---|---|---|
| **0A** displacement instrumentation | ✅ landed + run | `neuro_core/retrieval_trace.py` (new); optional `trace=` in `index.hybrid_search`, `rerank.Reranker.rerank`, `query.Engine._retrieve`/`retrieve_traced`; `scripts/retrieval_displacement.py` (new) | 10 new unit tests; full neuro_core suite green incl. byte-identical-to-today |
| **1-C** cite-what-you-used | ✅ landed | `qa.py` (cite only `[L#]` actually emitted; drop lane if none), `synth.py::cited_marker_numbers` (new) | new qa tests |
| **1-C** kill single-article fallback | ✅ landed | `standardize.py` (abstain instead of admitting low-tier) | updated augmentation test |
| Broad regression check | ✅ | 255 passed across touched modules + dependents (17s scoped run) | — |
| **0B** placebo/scramble eval | ⏳ next | — | — |
| **1-D** dynamic-K + MMR retrieval fix | ⏳ held until 0B; design = relevance-relative cut + MMR same-book penalty + widen `RETRIEVE_K` (NOT a raw score floor, NOT per-book quotas) | — | — |

Additive, flag-free changes so far are behavior-preserving on the untraced path (the
instrumentation does nothing unless a `trace=` is passed). The retrieval *behavior* change
(1-D) is deliberately not started — 0A says the fix is "stabilize which passages survive,"
and 0B will say whether the literature lane's gain is real before any lane-shaping work.
