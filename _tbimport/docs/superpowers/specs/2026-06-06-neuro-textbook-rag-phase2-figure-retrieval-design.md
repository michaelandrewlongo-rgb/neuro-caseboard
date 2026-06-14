# Neuro Textbook RAG — Phase 2: Visual / Figure Retrieval (Approach A)

**Date:** 2026-06-06
**Status:** Design approved; ready for implementation plan.
**Builds on:** Phase 1 (`2026-06-06-neuro-textbook-rag-design.md`) — text RAG over 14 neurosurgery
textbook PDFs, with a stable `query(question) -> {answer, citations[]}` seam.

## Goal

Make anatomy and imaging questions answerable from the figures in the corpus — Rhoton/Fukushima
dissection plates, neuroradiology figures, diagrams. When the user asks a visual question the system
should **both**:

1. **Surface the figure itself** (the plate, with caption + book/chapter/page), so the user can look
   at it, and
2. **Reason over the figure** — a vision model reads the relevant page image(s) and synthesizes a
   cited text answer.

This is Phase 2a. The phone/web access layer remains a separate later piece (Phase 2b), though the
Streamlit viewer built here is its seed.

## Decisions (locked during brainstorming)

- **Approach A — page-image augmentation of Phase 1.** Reuse the existing text/hybrid retrieval;
  attach figure-bearing page images to synthesis. Approaches B (BiomedCLIP per-figure visual
  embeddings) and C (ColPali/ColQwen late-interaction) are documented fallbacks, used only if the
  retrieval gate shows recall gaps.
- **Retrievable/displayed unit is the whole page**, not a cropped figure. Robust extraction; the
  caption and figure travel together. (Cropping is out of scope / fallback.)
- **Display = minimal Streamlit page**, served on the LAN so it is reachable from the user's phone.
- **Synthesis backend unified on Vertex AI Gemini** so calls draw on the user's finite ~$233 GCP
  trial credit. OpenRouter kept behind a config switch as fallback for when the credit runs out.
- **Cost-aware defaults** (credit is finite, but quality matters): default to a **Gemini Flash-tier**
  multimodal model (Pro available via config for hard cases); attach page images **only for
  figure-bearing top hits**, capped at **3 images**, rendered at **DPI ~150–180**. All tunable.

## Architecture & data flow

Everything extends Phase 1; nothing is replaced. The `query()` seam stays, gaining a `figures` field.

### Index-build time (one extra pass over the PDFs)

1. *(existing)* Extract page text + TOC-derived chapters.
2. **NEW — figure detection** (`engine/figures.py`): per page, flag pages that contain a real figure
   — ≥1 embedded image whose area ≥ a threshold (% of page) so logos/inline icons don't count. Pull
   the caption line (e.g. `Figure 12-3: …`) where present.
3. **NEW — page rendering:** render each figure-bearing page to a cached PNG (DPI ~150–180) under
   `assets/figures/<book>/p<NN>.png`. Skip if already on disk → this pass is crash-resumable.
4. *(existing)* Chunk → BGE embed → LanceDB, **plus** new columns `has_figure`, `figure_path`,
   `caption`; the caption text is folded into the embedded + FTS-indexed text so plate labels become
   searchable.

### Query time

1. *(existing)* Embed query → hybrid search (vector + FTS + RRF) → cross-encoder rerank → top passages.
2. **NEW:** for top hits whose page has a figure, load the cached page PNG, capped at `MAX_FIGURE_IMAGES`
   (default 3).
3. **NEW — multimodal synthesis:** send question + text passages + page images to Vertex Gemini. Same
   Phase 1 guardrails, extended: cite book/chapter/page, **describe the relevant figure**, refuse if
   not found ("Not found in the provided sources."), surface textbook disagreements.
4. **Result:** `QueryResult{ answer, citations[], figures[] }`, where each figure is
   `{book, chapter, page, image_path, caption}`.
5. **Display:** the Streamlit page renders answer (markdown) + citations + figure thumbnails.

## Components (units, each with one clear job)

- **`engine/figures.py` (new)** — figure detection + page rendering. Input: a PDF page. Output:
  `{has_figure, caption, image_path}`. Pure, testable in isolation; no LanceDB or model dependency.
- **`engine/ingest.py`** — calls `figures.py` during ingest; extends the coverage report with per-book
  figure-page counts.
- **`engine/index.py`** — schema gains `has_figure`, `figure_path`, `caption`; caption folded into
  indexed text. `hybrid_search` logic unchanged — figures ride along on returned rows.
- **`engine/synthesize.py`** — accepts optional page images; builds a multimodal Gemini request;
  guardrails extended for figures. Backend swappable: `provider = vertex | openrouter`.
- **`engine/query.py`** — `QueryResult` gains `figures[]`; orchestration loads page images for
  figure-bearing top hits and passes them to synthesis.
- **`cli/ask.py`** — prints answer, citations, and figure file paths.
- **`app/streamlit_app.py` (new)** — text box → `query()` → renders answer + citations + figure images
  with `Book — Chapter — p.N` and caption. Served on the LAN.

## Validation gates (blinded, proven before integration)

1. **Figure-retrieval gate** — `eval/figure_answers.yaml`: ~8–12 visual questions, each annotated with
   expected book + page/plate. Measure recall@k that the correct figure-page is surfaced.
2. **Figure-synthesis gate** — blinded faithfulness: does the multimodal answer match what the cited
   figure actually shows? Run a handful via an independent checker (same pattern as the Phase 1
   neurosurgeon-agent validation). This is the go/no-go before trusting the feature.
3. **Ingest gate (extended)** — per-book figure-page counts in the coverage report, so a book whose
   figures silently fail to detect is caught.

## Configuration

New `.env` / `config.py` keys:

- `SYNTH_PROVIDER=vertex` (fallback `openrouter`)
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `VERTEX_MODEL` (Flash-tier default; exact id
  confirmed at implementation — do not hardcode a guess)
- `MAX_FIGURE_IMAGES=3`, `FIGURE_DPI` (~150–180), figure-area threshold
- Auth via Application Default Credentials (`gcloud auth application-default login`)

New dependencies: `streamlit`, `google-genai` (Vertex). PyMuPDF already present.

**Re-index required:** the new columns mean one re-ingest + rebuild. Figure detection/rendering is
itself resumable (cached PNGs); the embed step keeps the existing non-resumable limitation. ~one-time
cost for 14 PDFs.

## Out of scope (documented fallbacks)

- Cropped per-figure extraction (whole-page display is the chosen unit).
- Approach B (BiomedCLIP per-figure visual embeddings) and Approach C (ColPali/ColQwen) — only if the
  figure-retrieval gate shows recall gaps.
- OCR for scanned/figure-only pages beyond the existing minimal fallback flag.
- Auth / multi-user web app (the Streamlit viewer is single-user, local-network).
- Phase 2b phone/web access layer as a distinct product.

## Known limitations carried forward

- Whole-page (not tightly cropped) display.
- Retrieval stays text-driven, so a caption-less, purely-visual page can be missed — exactly what
  Approach B would later address.
- Citations list still reflects retrieved passages, not only those the model cited (inherited from
  Phase 1).
