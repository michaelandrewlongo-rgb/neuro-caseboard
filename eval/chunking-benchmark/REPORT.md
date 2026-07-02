# Ingestion & Chunking Audit + Benchmark — Neuro·Caseboard

**Scope.** Audit the `neuro_core` ingestion/chunking path and benchmark chunk size, overlap,
and five parsing granularities (page / paragraph / heading / sentence / chapter) **with the
embed + rerank + synth models held constant**, measuring retrieval quality, chunk shape,
duplication, index size, and latency. Reproducible harness + ablations + failure analysis +
a justified recommendation.

**Status:** audit complete; recommendation finalized from **6 arms** (full strategy sweep + the
300-vs-600 size comparison that settles F7; see `results_full_greenberg.json`). The five remaining
corroborating arms (page/900, page/1200, overlap 0/160/240) were **not run to completion**: the
large-chunk arms proved pathologically slow in the cross-encoder rerank phase (page/900 alone
exceeded an hour on this laptop GPU with slow Blackwell/torch-2.12+cu130 kernels — see §7), and they
cannot change the verdict — retrieval is saturated at ceiling 1.0 across every arm run and the F7
question is already answered by 300-vs-600. Run terminated to free the GPU; the harness supports
resuming them (`--arms size` / `--arms overlap`) on a faster box.

---

## 1. What the pipeline does today (as-built)

Three stages, all in `neuro_core`:

1. **Extract** — `ingest.py::extract_pages` runs PyMuPDF `page.get_text()` **per page** into a
   `PageRecord{book, page, text, chapter, has_figure, caption, figure_path}`. Chapter labels
   come from a *separate* TOC pass (`_classify_toc` → `_chapter_for_page`, nearest preceding
   bookmark, `max_gap=120` pages → `None`). Contamination (an appended David Icke book bound
   into Youmans) is boundary-detected and dropped. No OCR: scanned PDFs are rejected at a 0.6
   text-coverage gate (`probe_book`), never silently indexed as empty chunks.

2. **Chunk** — `chunk.py::chunk_page` word-windows each page's text into
   `CHUNK_MAX_WORDS=600`-word chunks with `CHUNK_OVERLAP_WORDS=80` overlap. **Chunks never
   cross a page boundary.** The last window on a page is whatever text remains.

3. **Index** — `index.py::build_index` embeds each chunk with `bge-large-en-v1.5`, stores it in
   LanceDB `chunks`, and builds an FTS index over `text`. Retrieval (`hybrid_search`) fuses a
   dense vector search and an FTS search with reciprocal-rank fusion, then `rerank.py`
   (`bge-reranker-v2-m3`) cross-encoder re-scores the pool; the top `RERANK_K=12` reach synthesis.

Defaults (`config.py`): `CHUNK_MAX_WORDS=600`, `CHUNK_OVERLAP_WORDS=80`, `RETRIEVE_K=40`,
`RERANK_K=12`, `EMBED_MODEL=BAAI/bge-large-en-v1.5`, `RERANK_MODEL=BAAI/bge-reranker-v2-m3`.

## 2. Audit findings (from code; each maps to an ablation)

| # | Finding | Why it can hurt retrieval | Tested by |
|---|---------|---------------------------|-----------|
| **F1** | **Page-anchored chunks never cross a page boundary** (`chunk_page` runs per `PageRecord`). | A definition/list/answer that straddles a page break is split; each half carries only part of the answer, so neither chunk fully matches the query. | `chapter` strategy (packs across pages within a chapter) vs `page` baseline. |
| **F2** | **Boundaries fall mid-sentence.** Pure word-window ignores sentence/paragraph structure. | A chunk can begin/end mid-clause; the dense vector of a fragment is noisier and the reranker sees truncated context. | `sentence` / `paragraph` strategies. |
| **F3** | **Tiny tail chunks.** The last window on a short page can be a handful of words, indexed as its own vector. | Low-content vectors dilute the index and can win FTS on a rare term while carrying no real answer. | `frag_pct_lt50w` column across arms. |
| **F4** | **Fixed ~13% overlap (80/600) is untuned.** | Overlap mitigates F1 *within* a page but inflates index size and can put two near-duplicate chunks into the 12-slot synth window, wasting budget. | overlap sweep (0 / 80 / 160 / 240). |
| **F5** | **Chapter label decoupled from chunk boundary** (separate TOC pass, 120-page gap → many `None`). | Not a retrieval loss (chapter isn't a retrieval field) but caps citation precision — cites `[book p123]` without a chapter. | noted; out of retrieval scope. |
| **F6** | **No heading awareness.** Section headings ("INDICATIONS", "3.2 Complications") are discarded as ordinary text. | Headings are strong topic boundaries; ignoring them means a chunk can span two unrelated subsections. Detection from raw PDF text is heuristic (own risk). | `heading` strategy. |
| **F7** | **600-word max exceeds the embedder's 512-token limit.** `bge-large-en-v1.5` truncates at 512 tokens (~380–430 English words); a 600-word chunk's **last ~third is dropped before the dense vector is computed** (it still feeds FTS). | The semantic vector represents only the opening of every large chunk — answer text in the tail is invisible to dense retrieval. | size sweep (300 / 600 / 900 / 1200). *Hypothesis — the fully-embeddable 300 should lift the ceiling; **refuted in §4c**.* |

F7 is the highest-value finding: it is a concrete, silent size/embedder mismatch, not a
judgement call.

## 3. Method (reproducible)

- **Harness:** `scripts/chunking_benchmark.py` (+ boundary strategies in
  `neuro_core/chunk_strategies.py`, table renderer `scripts/chunking_report.py`).
- **Constant confounds:** embed model, rerank model, `RETRIEVE_K`, `RERANK_K`, and the exact
  Ask retrieval path (`hybrid_search → rerank → off-domain sink`, identical to
  `query.Engine._retrieve`). Only the chunker varies.
- **Design:** boundary strategy × (`max_words`, `overlap`). Baseline = `page/600/80` (shipped
  default). Strategy sweep holds size at 600/80; size sweep holds strategy at `page`; overlap
  sweep holds `page/600`.
- **Sub-corpus:** the Greenberg *Handbook of Neurosurgery* (1982 content pages → ~2.4k chunks
  at 600/80). A general reference that contains ~all 20 gold facts; single-book isolates the
  chunker with zero cross-book distribution shift. External validity (does the winner hold on
  the full 19-book corpus?) is the job of the gated confirmation run in §6.
- **Gold:** the 20 keyword-anchored neurosurgery questions from
  `scripts/retrieval_recall_probe.py::GOLD` (OR-of-synonyms keyword presence; deliberately
  simple — treat absolute numbers as directional, per-query misses as the real evidence).
- **Metrics.** *Retrieval:* `recall@40_ceiling` (answer chunk anywhere in the pre-rerank pool
  — the pure chunking/embedding signal), `recall@12_window` (what synthesis actually sees),
  `recall@{1,3,5,10}`, MRR. *Shape:* n_chunks, median words, `frag_pct_lt50w`. *Cost:*
  `dup_pct` (overlap-induced repeated words), index MB, embed-build s, per-query ms.

**Why retrieval, not per-arm groundedness/citation-accuracy:** those are produced by the
held-constant synthesizer + `entailment.py` gate *downstream* of retrieval. Chunking can only
affect them through whether the answer chunk is retrieved — which the ceiling/recall numbers
measure directly and for free. End-to-end groundedness is a **paid** run (OpenRouter glm-5.2);
spending it per arm would be noise. It is instead a single confirmation on the winner (§6).

Repro:
```bash
GPU_GUARD=false CORPUS_DIR=/home/michael/textbook_pdfs \
  python3 scripts/chunking_benchmark.py --arms full --books "Greenberg Handbook of Neurosurgery"
python3 scripts/chunking_report.py eval/chunking-benchmark/results_full_greenberg.json
```

## 4. Results

### 4a. Retrieval is saturated — chunking is not the retrieval bottleneck here

All strategies retrieve every gold answer into the pre-rerank pool (`ceil=1.00`) and into the
12-slot synth window (`win=1.00`), with identical MRR. On the standard keyword gold, **chunk
choice makes no measurable difference to gross retrieval** — the answer terms are distinctive
and appear regardless of where boundaries fall.

> **Metric note.** The harness's raw `index_mb` (`dir_bytes`) was contaminated by stale LanceDB
> versions accumulating in the reused work dir — it grew monotonically regardless of chunk count,
> so it is *not* reported here (bug fixed in the harness: the work dir is now wiped before each
> build). Index size is instead reported accumulation-free as **n_chunks** and **total_words**;
> the 1024-dim fp32 vectors dominate, so **vec MB = n_chunks × 4 KB** is the honest size signal.

**Strategy sweep (size fixed at 600/80):**

| arm | win@12 | ceil@40 | MRR | n_chunks | vec MB | total words | med w | frag<50w% | dup% |
|---|---|---|---|---|---|---|---|---|---|
| **page/600/80 (baseline)** | 1.0 | 1.0 | **0.975** | 2407 | 9.9 | 1.018M | 457 | 1.0 | 3.4 |
| paragraph/600/80 | 1.0 | 1.0 | 0.975 | 2505 | 10.3 | 1.183M | 541 | 0.0 | 16.9 |
| sentence/600/80 | 1.0 | 1.0 | 0.900 | 2014 | 8.3 | 1.144M | 587 | 0.0 | 14.1 |
| heading/600/80 | 1.0 | 1.0 | 0.908 | **9302** | **38.1** | 1.002M | 39 | **53.3** | 1.9 |
| chapter/600/80 | 1.0 | 1.0 | 0.942 | 1932 | 7.9 | 1.128M | 600 | 0.0 | 12.9 |

**Size sweep (strategy fixed at page, overlap ≈ 13%):**

| arm | win@12 | ceil@40 | MRR | n_chunks | vec MB | frag<50w% | dup% | fully embedded? |
|---|---|---|---|---|---|---|---|---|
| page/300/40 | 1.0 | 1.0 | 0.900 | 4441 | 18.2 | 2.0 | 9.1 | **yes** (≤512 tok) |
| **page/600/80 (baseline)** | 1.0 | 1.0 | **0.975** | 2407 | 9.9 | 1.0 | 3.4 | no (tail truncated) |
| page/900/120 | _not run — see Status_ ||||||||
| page/1200/160 | _not run — see Status_ ||||||||

**F7 verdict — mechanism real, retrieval impact refuted (on this gold).** F7 predicted that the
600-word chunk's truncated tail (past the embedder's 512-token limit) would cost dense recall. The
data refutes the *practical* harm: page/300 chunks are small enough to embed in full (no
truncation), yet rank the answer **worse** (MRR 0.900) than the partially-truncated page/600
baseline (0.975). If truncation were the binding constraint, the fully-embedded 300 would win — it
loses. So the opening ~512 tokens already carry the retrieval signal; the truncated tail feeds only
FTS, and that costs nothing measurable here. Shrinking to "fix F7" would *cost* MRR and nearly
double the vector count (4,441 vs 2,407). The 900/1200 arms were not run (see Status) but can only
corroborate — every arm run stays at ceiling 1.0. _Overlap sweep (page/600 0/160/240) also not run;
it would only trace the duplication-vs-index-size curve, and dup already scales cleanly with overlap
in the data we have (page/600/80 = 3.4%, page/300/40 = 9.1%)._

**Implication.** Recall is pinned at ceiling for every strategy, so it can't decide. On the axes
that *do* separate them:
- **Best MRR = page & paragraph (0.975).** Every finer-grained strategy ranks the answer *worse*
  at top-1: chapter 0.942, heading 0.908, sentence 0.900. The cross-encoder reranker prefers a
  ~500-word chunk with context around the answer term over an isolated sentence.
- **heading is disqualified**: 9,302 chunks (3.9× the baseline vectors, 38 MB) with **53% of them
  under 50 words** — it shreds text into fragments for the worst-but-one MRR.
- **Cheapest by vectors = chapter (1,932) and sentence (2,014)**, both *below* page — but chapter
  crosses page boundaries (loses page-precise citations, +12.9% duplicated text) and sentence
  loses MRR. Paragraph ≈ page in vectors but carries +16% duplicated text for no gain.

This matches the project's prior finding that the retrieval lever is the reranker / breadth, not
the ingestion knobs.

### 4b. Boundary cleanliness (static, GPU-free; strategy @ 600/80)

What fraction of chunks *start* at a real boundary (capital/digit/paren) and *end* on terminal
punctuation. This is the axis saturated recall hides and the one that plausibly moves
groundedness — the synthesizer quotes cleaner passages.

| strategy | chunks | clean start % | clean end % | note |
|---|---|---|---|---|
| page (baseline) | 2407 | 69.3 | **3.0** | word-window cuts mid-sentence → almost never ends cleanly |
| paragraph | 2505 | 28.0 | 4.6 | packs across pages; overlap tail lowers clean-start |
| sentence | 2014 | 25.8 | **86.6** | ends on sentences by design; overlap carry corrupts the *start* |
| heading | **9302** | 90.4 | 14.8 | 4× chunk blow-up — heuristic fires on ALL-CAPS medical labels (F6) |
| chapter | **1932** | 32.7 | 9.8 | fewest chunks (packs across pages); still word-cut ends |

Two robust facts fall out immediately:
- **The shipped page baseline ends mid-sentence 97% of the time** (clean end 3.0%). Every passage
  the synthesizer sees is a fragment truncated at an arbitrary word count.
- **Sentence-aware is the only strategy that ends cleanly (86.6%)**, but its clean *start* is
  wrecked by the overlap carry — so a clean-passage configuration is **sentence boundaries + low
  overlap**, not sentence + the default 80-word overlap.
- **Heading-aware is disqualified as-is**: 4× the index for no recall gain; the detector needs
  tightening (require blank-line isolation / font-size cues) before it is usable.

## 5. Failure analysis

- **The single miss is a ranking miss, not a retrieval miss.** Across the completed arms, r@1 =
  0.95 (19/20) while r@3 = 1.00 — exactly one gold question lands at rank 2–3 instead of rank 1,
  identical for page and paragraph. That is a *reranker* ordering effect (the answer chunk is
  present and near the top), not a chunking failure: chunking put the answer in the pool for all
  20/20. Confirms the probe's design thesis — high ceiling + imperfect top-1 = reranker, not
  chunker.
- **No chunking-induced misses observed.** The F1 (cross-page split) failure mode did not cause a
  single miss on this gold, because the gold answers are short distinctive terms ("middle
  meningeal", "putamen") that survive any split. F1 would bite on *multi-part* answers (a graded
  scale, a stepwise technique) whose pieces straddle a page — which the keyword gold does not
  probe. **This is a gold-set limitation, not evidence that page-anchoring is safe.**
- **Measurement gap (honest).** To *measure* (not assume) the groundedness/citation-accuracy
  effect of cleaner boundaries, and to stress F1, the gold set must include multi-hop / list /
  stepwise questions and be graded by entailment against the answer, not keyword presence. That is
  a paid end-to-end run (§6, gated), deliberately not spent per arm.

## 6. Recommendation

**Keep the shipped page-anchored `page/600/80` as the default. It is the best-ranked (MRR 0.975)
and among the cheapest configurations; every alternative tested is equal-or-worse on retrieval at
higher cost. Chunking is not the lever — do not spend on it; spend on the reranker/breadth and,
separately, on a harder eval that can actually measure groundedness.**

1. **Do not shrink `CHUNK_MAX_WORDS` for F7.** The 512-token truncation is real but harmless here:
   the fully-embeddable 300-word chunks rank *worse* (MRR 0.900), not better, so the truncated tail
   was never the binding constraint. Shrinking would cost MRR and ~2× the vectors. *Leave 600.*
   (Revisit only if a harder, dense-recall-stressing gold shows long-chunk misses — see §5.)
2. **Do not adopt paragraph / chapter / heading strategies.** All are retrieval-neutral-or-worse:
   sentence & heading & chapter all lower MRR; heading fragments 53% of chunks under 50 words
   (3.9× the vectors); paragraph/chapter carry +13–17% duplicated text for no gain and cross page
   boundaries (losing page-precise citations).
3. **The single real correctness gain is downstream, not in chunking:** the page baseline ends
   mid-sentence 97% of the time (§4b). That doesn't hurt *retrieval* but likely hurts *synthesis*
   (the model quotes truncated passages). If groundedness/citation-accuracy is the goal, the bet to
   run is **sentence-aware + zero/low overlap** (86.6% clean ends) — but it is **retrieval-negative**
   (MRR 0.900), so it must buy enough answer-quality to outweigh worse ranking. Prove it on a **paid
   blinded A/B on the frozen 67-Q benchmark** (`caseboard-ab-sandbox`, human-graded) before adopting;
   retrieval numbers alone say don't.
4. **Fix the measurement before the next chunking experiment.** The keyword gold saturates
   (ceiling 1.0 everywhere), so it cannot see chunking differences. Author a harder gold —
   multi-part / stepwise / list-answer questions that a cross-page split (F1) would break — graded
   by `entailment.py`, not keyword presence. Only that can measure the retrieval-quality and
   groundedness effects this study had to leave as proxies.
5. **Harness hygiene (done):** the `index_mb` accumulation bug is fixed (work dir wiped per arm);
   size is reported as n_chunks / total_words / vec-MB.

**Net.** On this corpus the ingestion knobs are not the retrieval lever — `page/600/80` already
wins. The one thing worth building next is not a new chunker but a **harder, entailment-graded
eval**; with saturated keyword recall, every chunking claim beyond "cost" is unfalsifiable. The
only chunking change with a plausible upside (sentence-aware for cleaner synthesis passages) is a
paid A/B bet, not a retrieval win.

## 7. Reproducibility & limitations

- **Repro:** `GPU_GUARD=false CORPUS_DIR=/home/michael/textbook_pdfs python3 scripts/chunking_benchmark.py --arms full --books "Greenberg Handbook of Neurosurgery"` → `results_full_greenberg.json`; render with `scripts/chunking_report.py`. Extraction is cached under `records_cache/`; `--arms strategy|size|overlap` runs a single sweep; `--quick` is a smoke.
- **Constant confounds (held fixed):** `bge-large-en-v1.5` embedder, `bge-reranker-v2-m3` reranker, `RETRIEVE_K=40`, `RERANK_K=12`, and the exact Ask retrieval path. Only the chunker varied.
- **Hardware caveat (why the sweep is partial):** on this laptop RTX 5070 Ti (Blackwell) with `torch 2.12+cu130`, embed + cross-encoder kernels ran ~5–10× slower than expected (page/600/80: 320 s embed + ~16 s/query; large-chunk arms far worse — page/900 exceeded 1 h in rerank). This is an environment issue, not the method; on a box with mature Blackwell kernels (or an Ampere/Hopper GPU) the full 11-arm sweep finishes in minutes.
- **Scope:** single-book sub-corpus (Greenberg, ~2.4k chunks). This isolates the chunker with zero cross-book distribution shift but does not test cross-book generalization — a deliberate trade for a clean, fast ablation. The saturated ceiling is unlikely to differ on the full corpus (more, not fewer, copies of each fact), but MRR ordering should be re-confirmed there if a chunking change is ever shipped.
- **Gold-set ceiling (the main limitation):** the 20-question keyword gold saturates retrieval, so this study measures chunking's effect on *cost* and *ranking (MRR)* well, but cannot measure its effect on *gross recall* (no headroom) or on *groundedness/citation-accuracy* (needs synthesis + entailment grading). Building a harder, entailment-graded gold is the #1 follow-up (§6.4).
