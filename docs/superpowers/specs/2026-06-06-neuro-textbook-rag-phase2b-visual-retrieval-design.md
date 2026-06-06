# Neuro Textbook RAG — Phase 2b: Visual Retrieval Lane (Approach B)

**Date:** 2026-06-06
**Status:** Design approved; ready for implementation plan.
**Builds on:** Phase 2a (`2026-06-06-neuro-textbook-rag-phase2-figure-retrieval-design.md`,
merged to `master`) — figure pages are detected, rendered to cached PNGs under `ASSETS_DIR`,
carried page→chunk→LanceDB→`Hit`→the `query()` seam, and attached as page images to a multimodal
Gemini call.

## Motivation

Phase 2a retrieval is **text-driven** (BGE + FTS over each page's text). On the first
`eval.figure_eval` run it scored 3/5: the two misses were **atlas plates** (Fukushima
petroclival/Meckel's cave; the neurovascular book's giant-ICA-aneurysm angiogram) whose pages exist
and were detected as figures, but whose page text didn't out-rank the figure pages of text-dense
operative books (Schmidek & Sweet, Rhoton). Figure *detection* works across all 14 books
(e.g. Fukushima 411/444 pages are figures); the gap is purely **ranking**: a great plate with terse
page text never surfaces.

**Goal:** add a visual retrieval lane so atlas plates surface on **image similarity** to the query,
fixing the misses — without disturbing the validated Phase 2a worded answer.

## Decisions (locked during brainstorming)

- **Local, swappable visual embedder.** Embeddings are computed on the GPU; the whole index stays
  on-box (consistent with Phase 1). Only query-time synthesis still uses Vertex. The model is
  swappable via `VISUAL_MODEL` so the figure gate picks the winner empirically. (Rejected: Vertex
  multimodal embeddings — would send thousands of copyrighted figure pages to Google at index time, a
  much larger egress than Phase 2a's query-time-only image sending.)
- **Figure selection only.** The worded answer + citations remain exactly what the Phase 2a text
  pipeline produces. The visual lane only changes which figure page(s) get displayed and fed to the
  vision model. (Rejected: folding visual hits into the main retrieval — perturbs the validated
  text-answer behavior and needs page/chunk granularity reconciliation.)
- **RRF-fuse the two figure rankings.** Candidate figures = figure-bearing `top` text hits + visual
  hits, fused by reciprocal rank fusion (the existing machinery) keyed by figure page, deduped, top
  `MAX_FIGURE_IMAGES`. Degrades gracefully: weak visual search → text-figure hits still fill in; text
  missed the plate → visual injects it. (Rejected: visual-primary backfill and quota-split — cruder.)
- **Whole-page image embedding.** v1 embeds the already-rendered page PNGs. Per-figure cropping is a
  documented future refinement.

## Architecture & data flow

The visual lane is a **parallel, additive retrieval path**. The Phase 1/2a text path — embed →
hybrid search → rerank → answer + citations — is untouched.

### Index-build time (reuses Phase 2a's rendered PNGs)

- A visual builder loads the cached figure-page PNGs, embeds each with the local CLIP-family model,
  and writes a **new LanceDB table `figures`** in the same `INDEX_DIR` — one row per figure page:
  `{id, book, chapter, page, figure_path, caption, vector}`.
- Because the PNGs already exist, this is a **standalone step** (`scripts/build_visual_index.py`)
  that does **not** re-render pages or re-embed text. It is also called at the end of
  `scripts/build_index.py` for fresh full builds.

### Query time (figure selection only)

1. Text path runs unchanged → `top` passages → answer + citations.
2. **Visual lane:** embed the question with the CLIP **text tower** → vector-search the `figures`
   table → top visual figure-page hits (`VISUAL_RETRIEVE_K`).
3. **RRF-fuse** two figure rankings keyed by `figure_path`: (A) figure-bearing `top` text hits,
   (B) visual hits. Dedupe, take top `MAX_FIGURE_IMAGES`.
4. **Citation assignment:** a selected figure whose `(book, page)` is already a cited passage reuses
   that source number (inline); a visual-only figure is appended as a new numbered source
   (`[k+1] Book, p.Y (figure)`), so the model can still cite it and it appears in the citation list.
5. Read image bytes (with the Phase 2a missing-PNG guard); feed aligned `figures, images` to the
   multimodal synthesis as today.

**Graceful fallback:** if the `figures` table is absent (index not yet upgraded), the visual lane is
skipped and behavior is exactly Phase 2a. The lane can also be turned off with `VISUAL_RETRIEVAL=off`
(used for A/B evaluation).

## Components

- **`engine/visual_embed.py` (new) — `VisualEmbedder`.** Thin `open_clip` wrapper; model from
  `VISUAL_MODEL`; injectable encoder + lazy load (mirrors `engine/embed.py`). `embed_images(paths)
  -> np.ndarray` (L2-normalized), `embed_query(text) -> vector` via the model's text tower.
- **`engine/visual_index.py` (new).** `build_visual_index(figure_pages, embedder, index_dir)` writes
  the `figures` table; `VisualIndex.image_search(query_vector, k) -> list[Hit]` reuses the existing
  `Hit` type (text = caption), so both lanes return the same shape.
- **`engine/index.py` — unchanged.** The module-level `reciprocal_rank_fusion(rankings)` is generic
  and is reused for figure fusion.
- **`engine/query.py` — `_collect_figures` rewrite.** Builds Lane A (figure-bearing `top` hits) and
  Lane B (visual hits), RRF-fuses by `figure_path`, dedupes, caps, assigns citations (reuse-or-append),
  reads bytes with the missing-PNG guard, returns aligned `figures, images`. `Engine` gains optional
  `visual_embedder` + `visual_index`; `get_engine` builds them but skips gracefully (Lane A only) when
  the `figures` table is absent or `VISUAL_RETRIEVAL` is off.
- **`engine/synthesize.py` — appended-source support.** Figures with `source_n > len(hits)` render in
  an "Additional figure sources" block and each gets a `Citation`. Backward-compatible (Phase 2a
  figures all reuse passage numbers → no appended block, citations unchanged).
- **`engine/config.py`** — `VISUAL_MODEL` (default BiomedCLIP), `VISUAL_RETRIEVE_K` (default 10),
  `VISUAL_RETRIEVAL` (default on).
- **`scripts/build_visual_index.py` (new)** — standalone builder over the existing index's figure
  pages and their cached PNGs; same builder wired into `scripts/build_index.py` for fresh builds.

## Validation gates (empirical, proven before integration)

1. **A/B the lane** — re-run `eval.figure_eval` with `VISUAL_RETRIEVAL=off` (Phase 2a baseline, 3/5)
   vs `on`; the pass criterion is the two atlas misses now surfacing plates.
2. **Model bake-off** — run the gate with `VISUAL_MODEL` = BiomedCLIP vs SigLIP (vs OpenCLIP); pick
   the winner by gate result, not by guess. Update `eval/figure_answers.yaml` expectations to encode
   the genuinely-correct source(s) per query (reality, not gamed-to-pass).
3. **Blinded synthesis review** — `eval.figure_eval --synthesize`: confirm the newly-surfaced atlas
   plates are the right figures and the answer faithfully describes them. Go/no-go.
4. **Unit/integration tests (TDD)** — `VisualEmbedder` (injected fake encoder → shape/normalization);
   `VisualIndex` real-LanceDB round-trip; `_collect_figures` RRF-fusion + citation assignment;
   `synthesize` appended-sources.

## Configuration & cost

- **No full re-index.** Phase 2a already wrote the figure PNGs, so validation starts with
  `python3 -m scripts.build_visual_index` (embeds existing PNGs into the `figures` table) — minutes,
  not a corpus re-embed.
- New `.env` keys: `VISUAL_MODEL`, `VISUAL_RETRIEVE_K`, `VISUAL_RETRIEVAL`.
- New dependency: `open_clip_torch` (local; first run downloads the chosen model's weights).

## Out of scope (documented future refinements)

- **Per-figure crops** — v1 embeds the whole rendered page; cropping to the figure bbox is the
  fallback if small-figure-on-text-heavy pages embed muddily (those are text-findable anyway).
- Cross-modal reranking of visual hits (RRF is enough for v1).
- Any change to the worded-answer path or the Streamlit viewer (the viewer already renders whatever
  figures return).
- Vertex/cloud-side image embeddings (rejected — keeps the index on-box).

## Known limitations carried forward

- Whole-page (not cropped) visual embedding: a small figure on a text-heavy page embeds muddily.
- A general/biomedical CLIP may be imperfect on surgical line-drawings — mitigated by `VISUAL_MODEL`
  swappability and the empirical model bake-off.
