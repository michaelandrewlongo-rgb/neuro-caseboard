# Run-log — Integrating *Practical Neuroangiography* (2026-06-18)

Integration of the textbook **Practical Neuroangiography** into the neuro-caseboard citation
corpus. Follows `docs/runbooks/integrating-a-textbook.md`.

- **Source PDF:** `/home/michael/textbook_pdfs/Practical neuroangiography.pdf` (40,807,482 bytes)
- **Book stem (citation key):** `Practical neuroangiography`
- **Active corpus:** `/home/michael/textbook_pdfs` — the PDF is **already staged** here.

## Step 1 — Probe (done, offline, no GPU)

```
$ python -m neuro_core.scripts.probe_book "/home/michael/textbook_pdfs/Practical neuroangiography.pdf"
[OK  ] Practical neuroangiography: 525p text=0.99 chapters=40 figpages=381 — text coverage 0.99 OK
exit: 0
```

| metric | value | meaning |
|---|---|---|
| pages | 525 | full book extracted |
| text coverage | **0.99** (519/525) | real text layer — **not** scanned; safe to index (≥ 0.6 gate) |
| chapters | 40 | detected from PDF bookmarks (e.g. "10 The Internal Carotid Artery") |
| figure-pages | 381 | rich figure/visual lane |

**Verdict: OK to index.** The #1 failure mode (scanned book / empty chunks) does not apply.

## Step 2 — Stage + byte-verify (done)

The PDF is already present in the active `CORPUS_DIR` at the size above; no copy needed. If
re-staging from a master folder, byte-verify with `stat -c%s src dst`.

## Steps 3–7 — Index build + validation (RUNTIME, human-gated — NOT run by this loop)

The text + visual index build mutates the **live** LanceDB index the web app serves, needs the
**system Python** (torch + CUDA + the `models` extra), and writes only to gitignored
`index/`/`assets/`. Run on the GPU host:

```bash
# 3. Text index (re-embeds the whole corpus; overwrite, no dup)
CORPUS_DIR=/home/michael/textbook_pdfs python -m neuro_core.scripts.build_index

# 4. Visual lane STANDALONE (avoids the in-process two-models-on-GPU OOM that leaves figures stale)
CORPUS_DIR=/home/michael/textbook_pdfs python -m neuro_core.scripts.build_visual_index
#    confirm: "Visual index built at /home/michael/neuro-textbook-rag/index" (exit 0)

# 5. Verify the book landed in BOTH tables (use to_arrow, not to_pandas)
python3 -c "import lancedb, collections as C; db=lancedb.connect('/home/michael/neuro-textbook-rag/index'); \
[print(t, C.Counter(db.open_table(t).to_arrow().column('book').to_pylist()).get('Practical neuroangiography',0)) for t in ('chunks','figures')]"

# 6. Validate: pytest; python -m eval.run_eval; python -m eval.figure_eval; one real in-domain query
# 7. Restart the server (it caches the index at startup) and check /ask + /figures
```

## Results — runtime build completed 2026-06-19

Indexed **incrementally** (only this book embedded, not the whole corpus) via the new `--book`
path — `CORPUS_DIR=/home/michael/textbook_pdfs python -m neuro_core.scripts.build_index --book "Practical neuroangiography"` — in **~1 min 47 s** (686 chunks embedded in 74 s + 381 figure pages). See PR #16 (incremental "add new books only" indexing).

| table | rows for `Practical neuroangiography` | table total (16→17 books) | notes |
|---|---|---|---|
| `chunks` | **686** | 28,022 → **28,708** (+686) | other 16 books' rows untouched |
| `figures` | **381** | 7,667 → **8,048** (+381) | whole-page mode → one row per figure page |

- Real query check: **PASS** — `text_search("digital subtraction angiography catheter technique")`
  surfaces the book at p71 (ch *3 Spinal Angiography: Technical Aspects*); `"vertebral artery
  origin angiographic anatomy"` at p230 (ch *15 The Arteries of the Posterior Fossa*). Chapter/page
  from bookmarks are correct.
- Live index backed up to `index.bak-2026-06-18` before the write (still present; remove once the
  app is confirmed good).
- Eval gates (`run_eval`, `figure_eval`) + server restart / `/ask` browser check: operator's to run.

## What this loop delivered (tracked, offline-testable)

- `neuro_core.ingest.probe_book` + `_probe_verdict` — scanned-book preflight guard.
- `neuro_core.scripts.probe_book` — CLI (`--corpus` to sweep the whole corpus).
- `docs/runbooks/integrating-a-textbook.md` — the repeatable repo runbook.
- This run-log.

The heavy GPU index build above is intentionally left to the operator (it mutates a live system).
