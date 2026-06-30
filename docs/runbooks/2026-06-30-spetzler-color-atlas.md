# Run log — Integrating *Spetzler Color Atlas of Microneurosurgery*

**Date:** 2026-06-30 · **Branch:** `add-book/spetzler-microneuro-atlas` · **Method:** single-book append (`--book`, `mode=append`)

Adds the 19th corpus book to the shared LanceDB index served by both the web app and the
`~/neuro-textbook-rag` viewer. `index/` + `assets/` are gitignored, so this doc is the only tracked change.

## Source

`/home/michael/textbook_pdfs/Spetzler Color Atlas of Microneurosurgery.pdf` (118,784,467 bytes, 603 pages).
Already inside the active `CORPUS_DIR` — no staging/copy needed.

## Resolved dirs (config)

| Dir | Value | Note |
|---|---|---|
| `CORPUS_DIR` | `/mnt/d/textbook_pdfs` (config default) → **exported `/home/michael/textbook_pdfs`** | default is stale; exported on every command |
| `INDEX_DIR` | `/home/michael/neuro-textbook-rag/index` | LanceDB `chunks`/`figures` |
| `ASSETS_DIR` | `/home/michael/neuro-textbook-rag/assets/figures` | rendered PNGs |

## Preconditions

- **Probe (no render):** coverage **0.977** (589/603 pages with text), **581 figure-pages** → real
  born-digital text layer, not a scan. Atlas was the high-risk input (image-first); probe cleared it.
- **Embed-model match (hard precondition):** index + config both `BAAI/bge-large-en-v1.5` (text) +
  `BiomedCLIP-PubMedBERT_256-vit_base_patch16_224` (visual). Append into a matching index → no NN poisoning.
- **`figure_crop=False`** → non-crop mode → expect one `figures` record per figure-page (1:1 with PNGs).

## Append

```bash
CORPUS_DIR=/home/michael/textbook_pdfs \
  python3 -m neuro_core.scripts.build_index --book "Spetzler Color Atlas of Microneurosurgery"
```

- `Corpus …: 19 PDFs; selected 1 to index [mode=append]` — exactly the new book.
- Text: 603 pages → **605 chunks** (~1 chunk/page — sparse, as expected for an atlas of captioned
  plates), embedded in 24s, `tbl.add` append.
- Visual: `Building visual index (581 figure pages) … [mode=append]` → `Visual index built.` (exit 0).
  In-process visual build (per the integrating-a-textbook skill); the standalone build was **not**
  run — it would overwrite all 18 books' figures. No OOM (single-book append, roomy GPU).

## Verification — by deltas (added the new book, touched nothing else)

| Table | Before | After | Δ | Expected Δ | New-book rows | Books |
|---|---|---|---|---|---|---|
| `chunks` | 41623 | **42228** | +605 | +605 | 605 | 18→19 ✓ |
| `figures` | 9786 | **10367** | +581 | +581 | 581 | 18→19 ✓ |

`figures` Δ (581) == figure-page count == rendered PNGs on disk (581) — correct for non-crop mode.
Totals grew by *exactly* the new book's counts → the other 18 books untouched.

## Validation (evidence)

- **Figure lane:** `select_figures("far lateral approach …")` selects Spetzler p590 + p43 interleaved
  with other books → visual-model compatible. Both PNGs exist: `…/Spetzler …/p0590.png` (3.2 MB),
  `p0043.png` (6.2 MB); all 581 PNGs present in `p%04d.png` scheme → `/figures` path will serve.
- **Text lane (self-retrieval):** querying a real Spetzler chunk (p312, orbitozygomatic/aneurysm
  caption) with its own words returns **that chunk at rank 1**, with Youmans (p6040) + Rhoton at 2–5
  → text embeddings live, correctly placed, interleaved with existing books → text-model compatible.
  (The atlas does *not* surface in generic "approach" queries — its thin caption text loses to dense
  prose textbooks. Expected atlas asymmetry, not a defect; its contribution is the figure lane.)
- **Eval gates:**
  - `eval.figure_eval` — **exit 0, no regression.** Every selected figure across the benchmark
    queries resolves to a real `<book>/pNNNN.png`; corpus figure retrieval intact. (Not a
    Spetzler-specific gate; the fixed queries are existing-corpus-tuned and the new book did not
    flip any to a hard failure.) Note: figure_eval is a **paid path** — it LLM-enriches each
    selected figure's caption/`claim` line via the OpenRouter `glm-5.2` synth client (the HTTPS
    socket observed). A handful of small completions, ~a few cents; not token-instrumented.
  - `eval.run_eval` — **skipped (hung, not run to completion).** It blocks making one LLM
    synthesis call **per benchmark question** (67); on this run it sat at 16 min wall / 6 s CPU,
    blocked in `wait_woken` on multiple ESTABLISHED `:443` sockets (network-throttled, not
    computing). Killed it. This is an eval-harness/network behavior **orthogonal to the append** —
    the append's correctness is already proven by the exact deltas + rank-1 self-retrieval +
    on-disk figures above. Re-run separately when the synth endpoint is responsive if a full
    answer-quality regression check is wanted.

## Notes / deviations

- Followed the **append** path of the `integrating-a-textbook` skill, which supersedes step 4 of the
  older `docs/runbooks/integrating-a-textbook.md` (that says run the visual build *standalone* — correct
  for a full rebuild, but for a single-book append the standalone overwrites every book's figures).
  In-process append worked cleanly here (exit 0, exact deltas).

## Go-live (operator)

Server caches the engine/index at startup — restart `scripts/serve.sh`, then confirm `POST /ask`
returns Spetzler and `GET /figures/Spetzler Color Atlas of Microneurosurgery/p0590.png` → HTTP 200.
This headless session verified the index/disk layer; the browser eyeball is the operator's.
