# Plan — P0 #2: Youmans chapter attribution + corpus-contamination guard

**Goal:** Stop systematically-wrong chapter metadata, and stop indexing non-medical contaminating
content, in `neuro_core/ingest.py` (the source of `PageRecord.chapter`, carried by `chunk.py`).

**Root cause (measured against the real PDF):** `Youmans and Winn Neurological Surgery.pdf` is 7865
pages with only **74 TOC bookmarks**, most of them junk or non-medical. `_chapter_for_page` assigns
each page the last bookmark whose start ≤ page, so huge un-bookmarked gaps inherit one distant label:
- 2353 pages → "25 - Positioning for Spine Surgery"  (the reported bug)
- 1821 pages → "300 - Radiosurgery for Intracranial Vascular Malformations"
- 1179 pages → a garbage bookmark "5yk4n23ycnpq9lc2…"
- **Pages ~6330–7865 are THREE copies of "Perceptions of a Renegade Mind" (David Icke COVID-conspiracy
  book)** — real indexable prose, bookmarked "Chapter N: …" / "Perceptions of a Renegade Mind". This
  non-medical content is in the corpus and gets indexed + is retrievable by a clinical tool.

**Verification reality:** the LOGIC is unit-testable (TOC fixtures) and locally validatable against the
real PDF (this machine). The durable fix — a clean source PDF and a full re-index — is OPERATIONAL
(needs the corpus + hours; can't run in CI). This slice ships the code guards + tests; the re-index is
flagged for the operator.

---

- [x] **Step 1 — Robust chapter attribution + contamination guard in `neuro_core/ingest.py`**
  - `_chapter_entries(doc)`: classify TOC entries. Keep only plausible **medical-chapter** bookmarks
    — Youmans chapters match `^\s*\d+\s*[-–]\s*\S` ("1 - History", "25 - Positioning…",
    "300 - Radiosurgery…"). Drop front-matter (Copyright/Dedication/Contents), duplicate title
    bookmarks ("_H. Richard Winn…"), garbage (random-string bookmarks), and the contamination
    bookmarks ("Perceptions of a Renegade Mind", `^Chapter \d+:` — Icke uses "Chapter N:" which is
    distinct from Youmans' "N - Title"). Return the kept medical entries AND the page of the first
    detected contamination/non-medical bookmark (the `content_end` boundary), if any.
  - `_chapter_for_page(entries, page, *, max_gap=…)`: **cap the gap** — if the nearest preceding
    medical bookmark is more than `max_gap` pages back (so the sparse TOC can't actually tell us the
    chapter), return `None` ("unknown chapter") instead of a confidently-wrong distant label. Honest
    "unknown" beats wrong. (Pick `max_gap` from the data — Youmans chapters are tens of pages, not
    thousands; ~120 is safe.)
  - Index-build exclusion: in `extract_pages` (or `build_index`'s page loop), **skip pages at/after the
    contamination boundary** (`content_end`) so the David-Icke pages are never indexed as medical
    chunks. Make the boundary detection data-driven (first non-medical bookmark), not a hardcoded page.
  - Tests `tests/neuro_core/test_ingest_chapter.py` (NEW): build a synthetic `get_toc()`-shaped fixture
    reproducing (a) the sparse-gap blanket → assert far pages get `None` not the distant label; (b) a
    contamination bookmark → assert its pages are flagged beyond `content_end` and excluded; (c) a
    normal densely-bookmarked book still labels correctly (no regression). Keep `test_chunk.py` green.
  - **Local validation (evidence, not CI):** re-run the chapter map over the real Youmans PDF and show
    the 2353-page "Ch 25" blanket and the conspiracy labels are gone (pages → honest None / excluded).
  - **Verify:** `PYTHONPATH=vendor/caseprep pytest -q tests/neuro_core/test_chunk.py tests/neuro_core/test_ingest_chapter.py` green; `npm --prefix web run build` green (if provenance.ts touched).

**Operator follow-up (flagged in PR, NOT in this slice):** re-source a clean Youmans PDF (or accept the
code exclusion) and **re-index** (`python -m neuro_core.scripts.build_index --book Youmans`) so the live
index reflects the corrected attribution and drops the contamination. Until then the live index still
contains the bad data; this slice only fixes go-forward indexing + metadata.
