# Cerebrovascular curated full-text corpus — design

**Date:** 2026-07-05
**Status:** approved, pending implementation plan

## Problem

The user hand-curated 508 full-text cerebrovascular journal articles into
`cv_full_text/` (PMID-named `.txt`/`.xml`/some `.pdf`, organized into 69
chapter folders mirroring a reference text's table of contents, indexed by
`have-list.csv`: pmid, chapter, format, file, access, year, journal, doi,
title, authors). The goal is to make these drawable as evidence in the Ask
pathway, cited like the existing corpus citation lanes.

## What already exists (discovered during brainstorming, not built here)

- **Lane C** (`neuro_caseboard/corpus.py`, merged PR #92) is a fully-built
  third evidence lane for the woven Ask path: BM25 over a contentless FTS5
  sidecar (`scripts/build_corpus_fts.py`) joined back to a read-only source
  SQLite (`works` / `identifiers` / `text_passages`), cited `[D#]`,
  composed into the prompt in `woven_synth.py` alongside `[n]` (textbook)
  and `[L#]` (live PubMed). It is additive/failure-safe: any error yields
  `[]`, never blocking Lane A.
- A sibling project, `/home/michael/PROJECTS/cv-curric` (a separate
  "Cerebrovascular Neurosurgery Curriculum" build), already produced a
  262,262-work, 2.5M-passage `cerebrovascular_fulltext.sqlite` (7.3GB) at
  `/mnt/c/dev/NSGY_DB_lean/fulltext/`, the exact path Lane C's default
  `CORPUS_SOURCE_DIR` expects, plus a pre-built FTS5 sidecar for it. This
  is a large automated PMC/PubMed pull, not curated by hand.
- Cross-checking confirmed **354 of the 508 `cv_full_text` PMIDs are
  already present** in that DB, fully extracted and section-tagged
  (`title`/`abstract`/`introduction`/`results`/`methods`/`conclusion`/
  `discussion`). The other **~154 are net-new**.
- `CORPUS_RETRIEVAL` is unset (Lane C is currently off for every request),
  and there is no per-request opt-in anywhere — not in `qa.py`'s public
  `answer_question()`, not in `AskRequest` (`api/server.py`), not in the
  web Ask UI. `CorpusConfig` is only ever built fresh from global env.

## Decision

Do **not** flip on the existing 262K-work automated corpus wholesale, and
do **not** write it into or depend on the sibling project's DB. Build a
small **standalone curated DB** from just the 508 hand-picked papers, and
add the missing per-request opt-in that lets a user flag a question as
cerebrovascular to unlock it. Rationale: the hand-curation is the value —
surfacing the noisier automated pull instead would dilute exactly the
quality signal the user already did the work to create.

## Design

### 1. Storage

New SQLite file `cv_curated_fulltext.sqlite`, schema-identical to Lane C's
existing tables (`works(id, title, normalized_title, pub_year,
journal_title, primary_domain, study_design, evidence_tier, abstract)`,
`identifiers(id, work_id, scheme, value)`,
`text_passages(id, work_id, section_type, content, sequence_number)`),
living at a new external data path following the CLAUDE.md convention of
live data outside the repo — `/home/michael/neuro-caseboard-corpus/fulltext/`.
A companion FTS5 sidecar is built the same way `build_corpus_fts.py`
already builds the other seven, reusing the existing
`~/.cache/neuro_caseboard/corpus_fts/` cache dir (keyed by DB name
`cv_curated`, alongside the other seven sidecars already there) rather than
inventing a second cache location. The new fulltext directory is entirely
separate from `/mnt/c/dev/NSGY_DB_lean/` — that stays read-only and
untouched.

### 2. Ingestion script: `scripts/build_cv_curated_corpus.py`

Driven by `have-list.csv` as the metadata source of truth (title, journal,
year, doi, pmid — never re-derived from file headers). For each of the 508
rows:

- **Already in `cerebrovascular_fulltext.sqlite` (354 PMIDs):** look up by
  PMID via its `identifiers` table, copy the matching `works` +
  `identifiers` + `text_passages` rows straight across into the new DB.
  No re-extraction, no re-tagging — that work is already done and correct.
- **Not present (~154 PMIDs):** every one already has a `.txt` (plaintext
  already extracted, whatever the original source), so no PDF/OCR work is
  needed. Where a sibling `.xml` (JATS/NLM full text) also exists, parse
  its `<sec>`/`<title>` structure for real section boundaries, mapped onto
  Lane C's fixed vocabulary (`title`, `abstract`, `introduction`,
  `methods`, `results`, `discussion`, `conclusion`, `case_report`,
  `other`). Where only `.txt` exists, fall back to a small regex
  header-splitter over common IMRAD headings; anything unmatched becomes
  one `other`-tagged passage for the whole article.
- Idempotent / re-runnable: skip PMIDs already present in the output DB
  (same pattern as `build_corpus_fts.py`'s "already built" skip), so
  re-running after adding more curated papers only processes the delta.
- After the DB is built, invoke (or extend) `build_corpus_fts.py` to
  produce the `cv_curated` FTS5 sidecar.

### 3. Per-request opt-in

- `AskRequest` (`api/server.py`) gains one new field:
  `cerebrovascular: bool = False`.
- `qa.answer_question()` gains a `corpus_config: CorpusConfig | None = None`
  passthrough parameter, threaded down to `_answer_question_woven` (which
  already accepts one — currently the public entrypoint just never passes
  it through).
- When `cerebrovascular=True`, the API layer builds an overridden config
  via `dataclasses.replace(load_corpus_config(), enabled=True,
  dbs=["cv_curated"], source_dir=<new fulltext path>, fts_dir=<new fts
  path>)` and passes it through. No global env change — `CORPUS_RETRIEVAL`
  and every other request's behavior is untouched.
- Web: one checkbox on the Ask page — "Cerebrovascular question (search
  curated full-text literature)" — threaded into `lib/api.ts`'s POST body
  for both the blocking and streaming Ask calls.

### 4. Citation style

Keep `[D#]`, exactly as Lane C already renders it (title/journal/year/PMID,
section tag). `woven_synth.py` already instructs the synthesis model to
keep `[n]` / `[L#]` / `[D#]` distinct — no new bracket style, no synthesis
prompt changes needed.

### Error handling

Follows Lane C's existing failure-safe contract: any error in the curated
corpus retrieval (missing sidecar, locked DB, bad query) yields `[]` and
never blocks Lanes A/B. The ingestion script must not fail its whole run on
one bad row — log and skip, matching `build_corpus_fts.py`'s per-DB
try/except pattern.

### Testing

- Ingestion script: a small self-check (`--selfcheck`, matching
  `corpus.py`'s pattern) that builds a tiny in-memory fixture DB from 2-3
  synthetic rows and asserts the copy-across path and the fresh-extraction
  path both produce well-formed rows.
- `qa.py` threading: one test that `answer_question(..., corpus_config=X)`
  actually reaches `retrieve_corpus_for_weave` with that config (not a
  freshly-loaded one).
- API: one test that `cerebrovascular=true` on `AskRequest` produces a
  `CorpusConfig` scoped to `dbs=["cv_curated"]`.
- No test drives the real 7.3GB external DB or the real curated DB in CI —
  both are external data, consistent with how the textbook/PubMed lanes
  are already tested (fixtures/mocks, not the live corpus).

## Out of scope

- Building or touching the other 9 subspecialty DBs / a generic
  multi-subspecialty selector UI. Only cerebrovascular was asked for;
  generalize when a second subspecialty is actually requested.
- Modifying `cv-curric` or its DB in any way.
- Re-extracting the 354 PMIDs already well-extracted in the big DB.
- Any change to the live PubMed lane (`[L#]`) or the textbook lane (`[n]`).
