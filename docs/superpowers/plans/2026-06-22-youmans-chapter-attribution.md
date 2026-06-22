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

---

## Review Findings (PR #57, slice-2 increment 6)

- [MUST] (none) — safety property empirically discharged across all 18 corpus books: `content_end`
  fires ONLY on Youmans (boundary 6330 = Icke title page); `None` chapter handled at every sink;
  off-by-one correct (keeps p6329, drops p6330+).
- [SHOULD] `neuro_core/ingest.py` `_is_random_token` (+ "cover" front-matter prefix) over-drops
  LEGITIMATE bookmarks → new mis-attribution: "Laminotomy/Foraminotomy/Discectomy" (Benzel),
  "Sedation/Analgesia/Anesthesia", "MYCOBACTERIAL/TUBERCULOSIS", "INDICATIONS/CONTRAINDICATIONS"
  (Bridwell ×5), "Diskectomy/Osteophytectomy" (Surgical Anatomy) — slash-joined section titles; and
  "Covered Stent Technique" dropped by the "cover" startswith prefix. Fix: `_is_random_token` should
  require a digit (real garbage "5yk4n23…" has digits) and/or treat `"/" in t`/purely-alphabetic as
  NOT random; make "cover" an EXACT match, not a prefix.
- [SHOULD] `tests/neuro_core/test_ingest_chapter.py` content_end-exclusion test is tautological
  (asserts `6330>=6330`, never calls `extract_pages`). The exclusion loop (ingest.py:151, the most
  safety-critical line) is untested. Fix: build a synthetic PDF via `doc.set_toc([...])` with a
  contamination bookmark and assert the contaminated pagenos are ABSENT from `extract_pages` records.
- [NIT] renegade contamination arm is position-independent — gate on `pg > last_medical` to remove the
  latent "contamination before medical content would truncate the book" footgun (zero-FP today).
- [NIT] `_chapter_entries` is now dead code (no callers) — remove it.

### Review tasks
- [ ] review: [SHOULD] fix `_is_random_token` to not drop slash-joined/alphabetic section titles
  (require a digit and/or treat "/" as non-random); make the "cover" front-matter filter an exact
  match not a prefix. Add a regression test asserting those real titles (e.g.
  "Laminotomy/Foraminotomy/Discectomy", "Covered Stent Technique") are KEPT.
- [ ] review: [SHOULD] replace the tautological content_end test with a real `extract_pages` test
  (synthetic PDF + set_toc contamination bookmark → assert contaminated pagenos absent from records).
- [ ] review: [nits] gate the renegade-mind contamination arm on `pg > last_medical`; remove the dead
  `_chapter_entries` function.
