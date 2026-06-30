# Task 3 — Index isolation run log

**Date:** 2026-06-29
**Branch:** sandbox/guidelines-testing (worktree)

## Part 1 — Backup / sandbox treatment arm  ✅ DONE (non-destructive)

Snapshot of LIVE `…/neuro-textbook-rag/index` before any change:

| table | books | guideline books |
|---|---|---|
| chunks | 60 | 42 |
| figures | 44 | 26 |

Copied the full live index dir → `…/neuro-textbook-rag/index-sandbox`
(`rsync -a --exclude='_backup_purge_*'`; excluded only the stale 641M internal purge backup
and the empty `index.sqlite`). Result = 1.1G.

Verified `index-sandbox`:
- chunks 60 books (42 guideline), figures 44 books (26 guideline) — matches live.
- Figure paths resolve on disk (incl. guideline-book figures) → shares `…/assets/figures`.

`index-sandbox` is now **both** the A/B treatment arm (60, guidelines) **and** the full backup
for the (pending) destructive revert.

## Part 2 — Revert LIVE to 18  ✅ DONE (destructive; authorized 2026-06-30)

1. `DELETE book LIKE 'GUIDELINES — %'` from live `chunks` + `figures`:
   - chunks: 60 books (42 guideline) → **18** (0 guideline)
   - figures: 44 books (26 guideline) → **18** (0 guideline)
2. Moved 42 `…/textbook_pdfs/GUIDELINES — *.pdf` → `…/guidelines_held/`:
   - live corpus 60 → **18** PDFs; held = **42**; remaining GUIDELINES in live corpus = 0.
3. Verified: live 0 guideline books / 18 total; sandbox intact 60 (42 guideline); sandbox
   figures resolve on disk; **live 18 ⊆ sandbox 60** (bit-identical textbook arms).

## Gate — retrieval-only smoke (no LLM spend), both arms  ✅ PASS

`eval.run_eval` is the **Build-dossier** harness (LLM + PDF per case), not a retrieval gate —
wrong/expensive instrument for this revert. Used the spec's retrieval-only smoke instead:

| query | LIVE (18) guideline hits | SANDBOX (60) guideline hits |
|---|---|---|
| ICH blood-pressure management | 0 (Youmans/NeuroICU) | 3 — AHA-ASA Spontaneous ICH 2022 |
| AIS endovascular thrombectomy | 0 (Decision-making/Greenberg/NeuroICU) | 2 — AHA-ASA Acute Ischemic Stroke 2026 |

Live clean at the retrieval layer; sandbox surfaces current-edition guidelines. Hard Gate met.

## Reversibility

Restore live to 60: `rsync -a --exclude='_backup_purge_*' …/index-sandbox/ …/index/` and
move PDFs back from `…/guidelines_held/`. LanceDB deletes are also versioned.
