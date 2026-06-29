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

## Part 2 — Revert LIVE to 18  ⏸ HELD (destructive — awaiting go-ahead)

Pending steps, to be run as the opening of the authorized Task 5 A/B session:
1. `DELETE book LIKE 'GUIDELINES — %'` from live `chunks` + `figures` → expect 18 / 18.
2. Move 42 `…/textbook_pdfs/GUIDELINES — *.pdf` → `…/guidelines_held/` → live corpus 18 PDFs.
3. Verify live clean (0 guideline books) + sandbox figures still resolve.
4. Run live eval gate (`python3 -m eval.run_eval`) — confirm 18-textbook baseline restored.

Rationale for holding: zero irreversible action while the shared repo/working dir is in active
use on another branch (`streaming-answers`); the revert's only consumer is the Task 5 baseline
arm, which needs its own (paid-run) go-ahead. Reversible via the `index-sandbox` backup.
