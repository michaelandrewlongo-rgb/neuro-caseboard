# Handoff — upstream textbook-rag figure work + ingest two new atlases

Goal: break the figure-relevance ceiling (blind image-judge ~5.7/10) by (A) cropping
**per-figure** plates in textbook-rag so semantic retrieval works, and (B) ingesting two
anatomy/approach atlases that fill the gaps the judge found. Target on the acceptance test:
**domain correctness ≥ 8.5 and specific relevance ≥ 8** (currently 7.8 / 5.7).

## Where things stand (neuro-caseboard)

- Repo: `/home/michael/projects/neuro-caseboard` (git, 164 tests). Pipeline:
  PLANNER→AUTHOR→CRITIC clinical depth (blind judge 4.8→7.2); textbook **grounding** wired
  (`retrieve.py` → textbook-rag `engine.index.Index.text_search`, no GPU); **figures** wired
  (`FigureCaptionRetriever` + region/level/domain guards in `retrieve.py`,
  `pipeline._collect_figures`).
- **Why this work exists:** figure *relevance* plateaued at ~5.7. Root cause (proven, see
  `eval/JUDGMENT.md` "Figure retrieval"): `figures.lance` embeds whole **page images**
  (text-dominated), not cropped plates, so BiomedCLIP **semantic** re-ranking is *worse*
  than caption-lexical (it returned a turbinate page for a CPA query, a pelvis page for
  C1-C2). Plus some ideal plates (V3-VA C1-C2 loop; a dedicated MCA-bifurcation clip plate)
  aren't indexed. Both are upstream/corpus problems, not retrieval-code bugs.

## Repos, paths, config (verified)

- **textbook-rag:** `/home/michael/neuro-textbook-rag` (git).
  - `CORPUS_DIR = /home/michael/textbook_pdfs` (effective), `INDEX_DIR = .../neuro-textbook-rag/index`,
    `ASSETS_DIR = .../assets/figures`, `EMBED_DEVICE = cuda` (**GPU available**),
    `FIGURE_DPI = 160`, `FIGURE_AREA_THRESHOLD = 0.1`,
    `VISUAL_MODEL = hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224`,
    `EMBED_MODEL = BAAI/bge-large-en-v1.5`. PyMuPDF 1.27, torch 2.12 (cuda), open_clip 3.3.
  - Index tables (LanceDB): `chunks` (text+FTS, ~22k), `figures` (~5.7k, page-image vectors), `books`, `meta`.
- **The two new PDFs are already in `CORPUS_DIR`:**
  `Brain Anatomy and Neurosurgical Approaches_ A Practical, Illustrated, Easy-to-Use Guide.pdf`
  and `Surgical Anatomy and Techniques to the Spine.pdf`. (Delete the `*.pdf:Zone.Identifier`
  sidecar files — Windows metadata.) These are exactly the cropped-figure-rich atlases the
  judge said the corpus is missing.
- neuro-caseboard reads the index via `CASEPREP_TEXTBOOK=1`; locations overridable with
  `TEXTBOOK_RAG_REPO` / `TEXTBOOK_INDEX_DIR`. Figures gated by `CASEBOARD_TEXTBOOK_FIGURES`.

## Task B — ingest the two new books (do first; simple, GPU-fast)

They're already in `CORPUS_DIR`, so:
```
cd /home/michael/neuro-textbook-rag
cp -r index index.bak           # build_index OVERWRITES the whole index
python -m scripts.build_index   # GPU; rebuilds chunks.lance + figures.lance for ALL PDFs
```
Verify: the coverage report lists both new books with `pages_with_figures > 0`; `figures`/
`chunks` row counts rise; `Index(INDEX_DIR).text_search("<topic from each book>", 5)` returns
hits from them. No neuro-caseboard code change — it reads the same index. Re-run
`python eval/coverage.py` and the figure report (below).

## Task A — crop per-figure plates (the real lever)

Current: `engine/figures.py::render_page_png` saves the **whole page**. Switch to cropping the
embedded figure region(s):
1. `engine/figures.py`: `page.get_image_info()` already gives raster **bboxes** (used in
   `figure_area_fraction`). For each (or the union of adjacent) bbox, crop with
   `page.get_pixmap(clip=fitz.Rect(bbox), dpi=...)` and save **one cropped plate per figure**.
   Keep the page render as a fallback for vector-only figures. Emit the plate path + bbox.
2. `extract_caption`: associate the caption text nearest each figure bbox (typically the line
   directly below it) and assemble the **full multi-line** caption — fixes the column
   truncation at the source (neuro-caseboard currently band-aids this in `captions.py`).
3. `engine/ingest.py::extract_pages`: emit **one record per figure** (book, chapter, page,
   `figure_path=cropped`, full caption, bbox), not one per page.
4. `scripts/build_index` → `build_visual_index` then embeds **cropped** plates → BiomedCLIP
   image embeddings are clean → semantic text↔figure works. Re-run the build.

Then in **neuro-caseboard**: add a semantic re-rank to `build_figure_retriever`
(`retrieve.py`) — embed the claim with the BiomedCLIP **text** encoder (CPU fine; see
`engine/visual_embed.py`), cosine vs `figures.lance` vectors, as a **hybrid** with the
existing caption-IDF lane. **Keep the region/level/domain guards** (cranial↔spine, CVJ-vs-
subaxial, peripheral-nerve, cortex, sellar, diagnostic-book exclusion, synonym expansion) —
they are good and orthogonal to ranking.

## Acceptance test (the loop's bar)

Ground truth: `eval/figure_cases.json` (3 cases: CPA VS, MCA-bif clip, C1-C2 Goel-Harms, each
with `figures_wanted` + `off_target`). Protocol:
1. Generate the 3 boards once with grounding+figures on (see header of `eval/figure_eval.py`)
   into `eval/_fig_boards/<id>/`.
2. `python eval/figure_eval.py` → writes `eval/FIGURE_REPORT.md` (figures attached per claim).
3. Dispatch a **blind, image-verifying** judge (it must open the page/plate PNGs, not trust
   captions) to grade each case on **domain correctness** and **specific relevance** (0-10)
   against `figure_cases.json`. Trajectory so far: page-text 8.3/4.7 → caption-rank 7.8/5.7.
   The cropping + atlases should clear the 5.7 ceiling.

## Key files

- textbook-rag: `engine/figures.py` (crop here), `engine/ingest.py`, `engine/visual_index.py`,
  `engine/visual_embed.py` (BiomedCLIP, CPU `encode_text`), `engine/index.py`
  (`Index.text_search`/`vector_search`/`hybrid_search`), `scripts/build_index.py`,
  `engine/config.py`.
- neuro-caseboard: `neuro_caseboard/retrieve.py` (`FigureCaptionRetriever`, `_figure_offtarget`,
  guards, `build_figure_retriever`, `_hit_to_dict`), `neuro_caseboard/pipeline.py`
  (`_collect_figures`), `neuro_caseboard/captions.py`, `eval/figure_cases.json`,
  `eval/figure_eval.py`, `eval/JUDGMENT.md` (figure section).

## Gotchas

- `build_index` rebuilds and **overwrites** the whole index — back up `index/` first.
- GPU (`cuda`) is available → fast; on CPU the text-embed pass is ~1 hr.
- `figures.lance` stores `page` as a string; there is no `printed_page` (PDF page only) → cite
  "Book, p.<pdf-page>".
- Keep neuro-caseboard's diagnostic-book exclusion (Neuroradiology Core Requisites, NeuroICU)
  and the region guards — they removed real off-target leaks.
