# Neurosurgery Textbook RAG — Design Spec

**Date:** 2026-06-06
**Status:** Approved design, pre-implementation

## Purpose

A personal, on-the-job reference tool that scans a folder of trusted neurosurgery
textbooks and answers clinical questions — management, diagnosis, surgical
indications, technique, and perioperative care — by synthesizing from the books
with verifiable citations. Decision-support, not a substitute for clinical
judgment.

## Corpus

- **Location:** `D:\textbook_pdfs` (WSL path `/mnt/d/textbook_pdfs`)
- **14 PDFs, ~2.1 GB** (one duplicate already removed by the user), spanning
  spine (Benzel, Bridwell, Vaccaro), vascular/endovascular (Harrigan-Deveikis,
  neurovascular decision-making), skull base/anatomy (Fukushima, Rhoton),
  general neurosurgery (Greenberg, Ellenbogen, Schmidek & Sweet), radiation
  oncology (CNS Rad Onc), neuroradiology (Core Requisites, Key Differential Dx),
  and neurocritical care (NeuroICU Book).
- **Verified:** all sampled books (including image-heavy Rhoton and Fukushima)
  have real text layers — thousands of extractable characters per page. This is
  a **text-extraction** project, not OCR. An OCR fallback is needed only for
  occasional scanned/figure-only pages.

## Scope decisions (settled during brainstorming)

| Decision | Choice |
|---|---|
| Architecture | Standalone, fresh — no dependency on the user's other projects |
| Answer engine | OpenRouter API (model swappable per cost/quality) |
| Embeddings | Local, on the user's GPU (private, zero per-query cost) |
| Access | Workstation now; clean engine seam so a phone/web layer is added later without rework |
| Approach | A (lean custom local RAG). C (visual/figure retrieval) is a documented phase 2 |

## Architecture

Two layers, deliberately decoupled:

- **`engine/`** — importable Python with no UI assumptions. Single public entry
  point: `query(question) -> {answer, citations[]}`. This is the seam the future
  phone/web layer (FastAPI) and the phase-2 figure retrieval attach to.
- **`cli/`** — thin `ask "question"` wrapper for use at the workstation now.

## Pipeline (Approach A)

### Ingest (one-time, idempotent / re-runnable)

1. `PyMuPDF` (already installed) extracts text **per page**.
2. Pull each book's embedded **table of contents / bookmarks** to label chapters
   for citations.
3. Flag pages with near-zero text as OCR candidates (deferred; rare in this
   corpus).
4. Produce **page-aware chunks** (~800 tokens, slight overlap) that never lose
   their page number, each tagged `{book, chapter, page}`.

### Index

- Local embeddings via `sentence-transformers`, model **BGE-large-en-v1.5**, on
  the GPU.
- Stored in **LanceDB** (embedded, on-disk), which provides **both** vector
  search and built-in BM25 full-text search — enabling true **hybrid retrieval**
  with no extra moving parts. Keyword matching matters in medicine (drug names,
  doses, eponyms must match exactly).

### Query

1. Embed question; run hybrid retrieval (semantic + keyword) for candidates.
2. **Local cross-encoder reranker** (BGE-reranker) selects the precise top
   passages.
3. **OpenRouter** synthesizes a grounded answer from the top passages.

## Safety / trust constraints

The synthesis prompt is constrained to:

- **Cite book + chapter + page for every claim.**
- **Say "not found in these sources" rather than guess.**
- **Surface disagreements between textbooks** instead of smoothing them over.

Output is the answer **plus the exact source passages** (with book/chapter/page),
so the user can open the PDF and verify. Framed explicitly as decision-support.

## Validation gates (each proven before integration)

1. **Ingest gate** — per-book page counts and text-coverage report; catches a
   silently-failed extraction.
2. **Retrieval gate** — a small known-answer question set (e.g., normal ICP
   range, a specific drug dose) must return the correct book/page.
3. **Synthesis gate** — blinded faithfulness check: does the generated answer
   match its cited passages?

## Configuration

- New standalone git repo at `~/neuro-textbook-rag`.
- `.env`: `OPENROUTER_API_KEY`, model name, corpus path, index path.
  (WSL caveat: strip trailing `\r` from `.env` values.)

## Phase 2 — Visual / figure retrieval (Approach C, deferred)

Extract page images and figures; add visual retrieval (e.g., multimodal/ColPali
or page-image input to a vision model) so anatomy and atlas questions (Rhoton,
Fukushima plates, radiology figures) are answerable. Attaches at the existing
`query()` seam; no rework of Approach A required.

## Out of scope (for now)

- Phone/web UI (seam left in place, not built).
- OCR pipeline beyond a minimal fallback flag.
- Any integration with the user's other projects.
