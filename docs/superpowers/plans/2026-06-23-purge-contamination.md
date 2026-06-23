# Plan — Corpus contamination: audit + eliminate every trace

**Goal (operator task, autonomous):** check the corpus for ANY contamination, then eliminate all trace.

## Audit findings (this session, read-only)
- **Single contaminated source:** David Icke's *"Perceptions of a Renegade Mind"* (2021) is appended to
  the **Youmans** PDF, indexed as Youmans **pages ≥ 6330** (chapter titles "Renegade perception", "Who
  controls the Cult?", "'Covid': The calculated catastrophe", …). Page 6310 is still legit Youmans; 6350 is
  David Icke ch1. The slice-2 `_classify_toc` `content_end=6330` sits exactly on the boundary.
- **Live-index inventory** (`/home/michael/neuro-textbook-rag/index`): **1497** `chunks.lance` rows + **69**
  `figures.lance` rows with `book="Youmans…" AND page>=6330`, plus their `_gemini_captions.jsonl` lines.
- **No other book is contaminated:** word-boundary conspiracy-marker scan across all 43,120 chunks hit only
  Youmans ≥6330. False positives ruled out: Bridwell "rothschild" = citation author *Rothschild B*; Youmans
  pre-6000 "reptilian"/marker hits = legit medical references (the index predates the slice-2 guard, so the
  contamination is still live).
- Root cause is the **source PDF**; the shipped slice-2 ingest guard already excludes pages ≥ content_end on
  any future re-index, so recurrence is prevented — but the *current* live index (built Jun 10, pre-guard)
  still carries the contamination. This task purges the live artifacts.

---

> **DESIGN CORRECTION (after dry-run on live):** detection is **index-based**, not PDF-TOC-based. The
> current Youmans PDF (Jun 20) has David Icke at PDF p7354+, but the index (Jun 10) has it at index p6330+
> (~1024-page offset) and `_classify_toc` returns None on the current PDF. So the boundary is derived from
> the indexed `chunks` (David-Icke chapter signature → contiguous tail → snap-back over front matter → last
> medical chunk), gated by a fail-safe purity check. Commits 07bb66c (initial) + 4e04116 (index-based rework).

- [x] **Step 1 — `neuro_core/scripts/purge_contamination.py` (re-runnable audit + guarded purge)**
  - DONE (4e04116): index-based `detect_contaminated_regions`; MIN_STRONG=15 gate; boundary snap-back;
    fail-safe purity check (region must be all-non-medical + have conspiracy markers, else excluded, never
    deleted); marker scan report-only; backup + content-boundary delete + caption fail-safe + idempotent.
    Hermetic test **6 passed** (incl purity + caption fail-safe).
  - **Detection (reuses shipped logic, generalizes — not Youmans-hardcoded):** for each book under
    `CORPUS_DIR`, open its PDF TOC and run `neuro_core.ingest._classify_toc` → `content_end`. A book with
    `content_end is not None` has an appended non-medical region starting at that page. CROSS-CHECK: scan
    the indexed chunk text for word-boundary conspiracy markers (`david icke`, `reptilian`, `illuminati`,
    `annunaki`, `freemason`, `\bicke\b`, "renegade perception", "who controls the cult", …) and report any
    book/page that the content_end boundary did NOT already cover (catches contamination with a different
    shape). Medical-term-density anomaly is a tertiary signal.
  - **`audit` (default, READ-ONLY):** print per-book `content_end`, contaminated chunk/figure counts, and
    any marker hits outside the boundary. Exit non-zero if contamination is found (so it's a usable gate).
  - **`--apply`:** (a) back up `chunks.lance`/`figures.lance`/`_gemini_captions.jsonl` to a timestamped
    sibling dir FIRST; (b) `chunks.delete("book = '<b>' AND page >= <content_end>")` and same on `figures`;
    (c) rewrite `_gemini_captions.jsonl` dropping lines for deleted figures (match book + page≥content_end
    via the `figure_path`/page field). Idempotent: re-running finds nothing to delete.
  - Use `INDEX_DIR`/`CORPUS_DIR` from `neuro_core.config` (env-overridable); never hardcode the absolute
    path. SQL-escape the book string in the delete predicate.
  - `tests/neuro_core/test_purge_contamination.py` (NEW, hermetic): build a tiny temp LanceDB with a
    "clean" book + a "contaminated" book (rows page<E medical, page>=E conspiracy markers) + a captions
    file; assert `audit` detects exactly the contaminated rows and reports the right counts; assert
    `--apply` deletes only page>=E rows of the contaminated book, leaves the clean book + page<E rows
    intact, filters the captions, backs up first, and is idempotent on a second run.
  - **Verify (code):** `cd <wt> && PYTHONPATH=vendor/caseprep python3 -m pytest -q
    tests/neuro_core/test_purge_contamination.py`.

- [x] **Step 2 — Dry-run audit on the LIVE index (no changes)** — DONE: live read-only audit reports
  Youmans boundary 6330, **1497 chunks + 69 figures**, purity OK, exit 1; only Youmans purgeable; 2
  out-of-region marker hits (Bridwell citation, 1 Youmans) report-only. Matches verified ground truth. GO.

- [ ] **Step 3 — Back up + APPLY the purge to the live index, then VERIFY clean**
  - Run `--apply`. Then verify: (a) zero chunks/figures with `book="Youmans…" AND page>=6330`; (b) zero
    word-boundary conspiracy-marker chunks remain anywhere; (c) legit Youmans content intact (chunk count
    ≈ 14412−1497, all medical chapters preserved, page<6330 untouched); (d) a `caseboard ask` smoke query
    on a vascular topic returns only medical sources; (e) the backup exists and is restorable. Re-run
    `audit` → exits clean (0 contamination).

**Safety:** destructive deletes are backed up first and gated behind an explicit `--apply` + a passing
dry-run audit. The script is committed (reviewable, re-runnable — "check for contamination" anytime). No
fabrication; the legit corpus is preserved exactly. Source-PDF cleaning is OUT of scope (the shipped ingest
guard already prevents re-contamination on re-index; noted as an optional operator follow-up).
