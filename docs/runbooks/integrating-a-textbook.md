# Runbook — Integrating a textbook into the neuro-caseboard corpus

Adding a book to the citation-grounded corpus is **stage the PDF into the active corpus, then
re-index** — there is no per-book code. Book identity is the PDF filename stem; chapters come from
the PDF's bookmarks. The text + visual index build is a **GPU runtime step that mutates the live
LanceDB index the web app serves** and writes only to the gitignored `index/` / `assets/` dirs, so
it is run by a human on the GPU host, not by CI or an automated loop.

> The build needs the **system Python** (torch + CUDA + the `models` extra:
> sentence-transformers / open_clip). The offline test venv deliberately lacks these.

## Active runtime locations (this machine)

The engine resolves dirs via `neuro_core.config.load_config()` (env → `.env` → DEFAULTS). The
DEFAULT `CORPUS_DIR` (`/mnt/d/textbook_pdfs`) is **stale** — always export the active one:

| Dir | Value |
|---|---|
| `CORPUS_DIR` | `/home/michael/textbook_pdfs` (the active corpus; export it) |
| `INDEX_DIR`  | `/home/michael/neuro-textbook-rag/index` (LanceDB: `chunks`, `figures`, `cards`) |
| `ASSETS_DIR` | `/home/michael/neuro-textbook-rag/assets/figures` (rendered figure PNGs) |

Confirm before doing anything:
```bash
python3 -c "from neuro_core.config import load_config as L; c=L(); print(c.corpus_dir, c.index_dir, c.assets_dir)"
```

## Step 1 — Probe before you spend GPU

The pipeline extracts text; it does **not** OCR. A scanned book (no text layer) yields empty
chunks. Probe first (cheap, no render, no GPU):
```bash
python -m neuro_core.scripts.probe_book "$CORPUS_DIR/<book>.pdf"   # one file
python -m neuro_core.scripts.probe_book --corpus                   # every PDF in CORPUS_DIR
```
Each line reports `coverage`, page count, chapter count, figure-page count, and an `OK`/`SKIP`
verdict. Exit code is non-zero if any book is below `MIN_TEXT_COVERAGE` (0.6). Do **not** index a
`SKIP` book.

## Step 2 — Stage the PDF + byte-verify

```bash
cp "<source>/<book>.pdf" "$CORPUS_DIR/"
stat -c%s "<source>/<book>.pdf" "$CORPUS_DIR/<book>.pdf"   # sizes must match
```

## Step 3 — Build the text index (system Python, GPU)

**Preferred — append a single book (~1.5 min for a 500-page book):**
```bash
CORPUS_DIR=/home/michael/textbook_pdfs INDEX_DIR=/home/michael/neuro-textbook-rag/index \
  python -m neuro_core.scripts.build_index --book "<stem>"
```
`--book` indexes only the named PDF stem and appends to existing tables (idempotent: re-running
replaces that book's rows rather than duplicating them). `--new-only` instead indexes every PDF
in `CORPUS_DIR` not already in the `chunks` table — useful after dropping in multiple new books.

**Full rebuild (only if you need to re-embed the entire corpus):**
```bash
CORPUS_DIR=/home/michael/textbook_pdfs python -m neuro_core.scripts.build_index
```
Rebuilds the `chunks` table with `mode="overwrite"` and re-embeds the **whole** corpus. Figure
rendering skips already-rendered PNGs, so only new pages render. Default (no flags) is always
overwrite — don't use it just to add one book.

## Step 4 — Build the visual lane STANDALONE (critical)

```bash
CORPUS_DIR=/home/michael/textbook_pdfs python -m neuro_core.scripts.build_visual_index
```
**Gotcha:** `build_index` also kicks off the visual build *in-process*, where the text model (BGE)
and the visual model (BiomedCLIP/CLIP) are co-resident on the GPU → it can be **SIGKILLed with no
Python traceback**. The text index still succeeds, so it *looks* done, but the `figures` table is
left **stale**. The standalone script loads only the visual model and is the reliable path —
always run it and confirm it printed `Visual index built at <index_dir>` (exit 0).

## Step 5 — Verify the book is in BOTH tables

Use `to_arrow()`, not `to_pandas()` (`to_pandas` needs `pylance`, often absent):
```bash
python3 -c "import lancedb, collections as C; db=lancedb.connect('/home/michael/neuro-textbook-rag/index'); \
[print(t, C.Counter(db.open_table(t).to_arrow().column('book').to_pylist()).get('<book-stem>',0)) for t in ('chunks','figures')]"
```
Expect `figures` rows **<** the rendered-PNG count — text-less pure-image plates produce no chunk
and aren't visually embedded. That gap is normal, identical across books, not a failed build.

## Step 6 — Validate (evidence, not assertions)

- `python3 -m pytest -q` (full suite; on this machine prefer the scoped offline subset — see
  `docs/runbooks/` notes — or run in a clean venv without the `models` extra).
- `python3 -m eval.run_eval` and `python3 -m eval.figure_eval` (retrieval gates). These are tuned
  to the existing corpus; if one flips because the new book legitimately outranks the old expected
  source, **investigate before editing the gate YAML** — don't game it.
- One real in-domain query through `neuro_core.query` (or the server `/ask`): confirm the answer
  **cites the new book** and **attaches one of its figures** with a correct book/chapter/page.

## Step 7 — Go live

The server caches the engine/index **at startup**; a running server keeps serving the **old**
index until restarted. Restart it, then check `POST /ask` returns the new book and
`GET /figures/<book>/<page>.png` → HTTP 200. (A headless session can hit the API but can't eyeball
the browser — that last visual check is the operator's.)

## Record

`index/` and `assets/` are gitignored, so the only tracked change is docs: write a dated run-log
under `docs/runbooks/` (commands, table counts, validation evidence, problems hit + recovery).
