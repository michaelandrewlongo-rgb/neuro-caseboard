# Integrate "Practical Neuroangiography" textbook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Each top-level `- [ ]` is ONE task = one subagent = one
> commit; run the TDD micro-cycle (write failing test → see it fail → implement → see it pass →
> commit) *inside* the task. Steps use checkbox (`- [ ]`) syntax for the driving loop.

**Goal:** Make *Practical Neuroangiography* a first-class, citable source in neuro-caseboard's
corpus, and harden + document the "add a textbook" path so this and future books integrate
reliably.

**Architecture:** Adding a book to this corpus is *stage the PDF + re-index* — there is no
per-book code (the corpus is a folder of PDFs; book identity = filename stem; chapters come from
PDF bookmarks). The heavy text+visual index build is a **GPU runtime step that mutates the live
LanceDB index the web app serves**, writes only to gitignored `index/`/`assets/`, and therefore
is OUT OF LOOP SCOPE (human-gated). The loop delivers the *durable, reviewable, offline-testable*
half: a `probe_book` preflight that encodes the skill's "don't index a scanned book" failure mode,
a small CLI for it, a repo-specific runbook, and an honest run-log for this book.

**Tech Stack:** Python ≥3.10, PyMuPDF (`fitz`) via `neuro_core.ingest`, LanceDB (runtime only),
pytest. No new dependencies.

## Global Constraints

- Python floor **3.10**; all loop tests are **offline / hermetic** (no network, no GPU, no real
  ML models — the loop venv has none).
- Run tests with the loop venv from the worktree root:
  `.loopvenv/bin/python -m pytest -p no:cacheprovider -q <paths>`. New tests MUST live under
  `tests/neuro_core/` so they fall inside the loop harness scope.
- No new third-party dependencies. No changes to the existing index/build *behavior* for books
  that already index cleanly (coverage ≈ 1.0 must stay byte-identical through the pipeline).
- Do NOT run `build_index` / `build_visual_index` inside the loop (mutates the live index;
  requires GPU + the `models` extra the loop venv intentionally lacks).

## Context (verified this increment — facts the implementer can rely on)

- **PDF:** `/home/michael/textbook_pdfs/Practical neuroangiography.pdf` — text coverage **0.989**
  (519/525 pages), **525 pages**, **40 chapters** (from bookmarks), **381 figure-bearing pages**.
  Already present in the active corpus dir. It is a real text-layer PDF (not scanned) → integrable.
- **Active runtime dirs** (config defaults are stale; see memory `runtime-engine-config`):
  `CORPUS_DIR=/home/michael/textbook_pdfs`, `INDEX_DIR=~/neuro-textbook-rag/index`,
  `ASSETS_DIR=~/neuro-textbook-rag/assets/figures`. `neuro_core.config.load_config()` reads
  env → `.env` → DEFAULTS, and DEFAULT `CORPUS_DIR` is the stale `/mnt/d/textbook_pdfs`, so the
  build commands MUST export `CORPUS_DIR`.
- **Ingest API** (`neuro_core/ingest.py`): `extract_pages(pdf_path, render=False)` →
  `list[PageRecord]` (fields incl. `.book`, `.page`, `.text`, `.chapter`, `.has_figure`);
  `coverage_from_records(records)` → `{book: {pages, pages_with_text, coverage, pages_with_figures}}`
  (a page counts as text if `len(r.text) > 50`).
- **Build scripts:** `neuro_core/scripts/build_index.py` (`main()`, `__main__`) re-embeds the whole
  corpus with `mode="overwrite"` and calls `build_visual_index` **in-process** (OOM-prone: text +
  visual model co-resident on GPU → SIGKILL with no traceback, leaving the `figures` table stale).
  `neuro_core/scripts/build_visual_index.py` (`main()`, `__main__`) loads only the visual model and
  prints `Visual index built at <index_dir>` — the reliable standalone path.
- **Test fixtures:** `tests/neuro_core/conftest.py` provides `tiny_pdf` (4 pages, coverage 1.0,
  chapters Introduction/Methods, book stem "Sample Book") and `pdf_with_figure`.

---

## Tasks

- [x] **Task 1 — `probe_book` preflight helper in `neuro_core/ingest.py` (TDD)**

  **Files:** Modify `neuro_core/ingest.py`; Test `tests/neuro_core/test_probe_book.py` (new).

  **Produces:** `probe_book(pdf_path, min_coverage=0.6) -> dict` with keys
  `book, pages, pages_with_text, coverage, pages_with_figures, chapters, ok, reason`; and a pure
  helper `_probe_verdict(coverage, pages, min_coverage) -> (bool, str)`.

  Add to `neuro_core/ingest.py`:
  ```python
  MIN_TEXT_COVERAGE = 0.6  # below this, treat the PDF as scanned (no usable text layer)

  def _probe_verdict(coverage, pages, min_coverage=MIN_TEXT_COVERAGE):
      """Pure go/no-go decision for a candidate corpus PDF."""
      if pages == 0:
          return False, "no pages extracted (unreadable or empty PDF)"
      if coverage < min_coverage:
          return False, (f"text coverage {coverage:.2f} < {min_coverage:.2f} — likely scanned "
                         "(no text layer); this pipeline does not OCR, indexing yields empty chunks")
      return True, f"text coverage {coverage:.2f} OK"

  def probe_book(pdf_path, min_coverage=MIN_TEXT_COVERAGE):
      """Cheap preflight (no render, no GPU) before an expensive index build.

      Encodes the #1 textbook-integration failure mode: silently indexing a scanned book.
      """
      recs = extract_pages(pdf_path, render=False)
      cov = coverage_from_records(recs)
      book = next(iter(cov), Path(pdf_path).stem)
      s = cov.get(book, {"pages": 0, "pages_with_text": 0, "coverage": 0.0, "pages_with_figures": 0})
      chapters = len({r.chapter for r in recs if getattr(r, "chapter", None)})
      ok, reason = _probe_verdict(s["coverage"], s["pages"], min_coverage)
      return {"book": book, "pages": s["pages"], "pages_with_text": s["pages_with_text"],
              "coverage": s["coverage"], "pages_with_figures": s["pages_with_figures"],
              "chapters": chapters, "ok": ok, "reason": reason}
  ```
  (Ensure `from pathlib import Path` is imported in `ingest.py`; it already imports `Path` — reuse.)

  Tests (`tests/neuro_core/test_probe_book.py`):
  ```python
  from neuro_core.ingest import probe_book, _probe_verdict

  def test_verdict_flags_scanned():
      ok, reason = _probe_verdict(0.10, 200, 0.6)
      assert ok is False and "scanned" in reason

  def test_verdict_flags_empty():
      ok, reason = _probe_verdict(0.0, 0, 0.6)
      assert ok is False and "no pages" in reason

  def test_verdict_passes_text_layer():
      ok, _ = _probe_verdict(0.99, 200, 0.6)
      assert ok is True

  def test_probe_book_on_tiny_pdf(tiny_pdf):
      rep = probe_book(tiny_pdf)
      assert rep["book"] == "Sample Book"
      assert rep["pages"] == 4
      assert rep["coverage"] == 1.0
      assert rep["chapters"] == 2
      assert rep["ok"] is True
  ```
  Verify: `.loopvenv/bin/python -m pytest -q tests/neuro_core/test_probe_book.py` → all pass.
  Commit: `feat(ingest): add probe_book preflight (scanned-book guard) for corpus PDFs`.

- [x] **Task 2 — `neuro_core/scripts/probe_book.py` CLI (TDD)**

  **Files:** Create `neuro_core/scripts/probe_book.py`; Test
  `tests/neuro_core/test_probe_book_script.py` (new).

  **Consumes:** `neuro_core.ingest.probe_book` (Task 1); `neuro_core.config.load_config`.
  **Produces:** `main(argv=None) -> int` (0 if every probed book is OK, 1 otherwise).

  ```python
  """Preflight corpus PDFs before an expensive GPU index build.

      python -m neuro_core.scripts.probe_book PATH.pdf      # one file
      python -m neuro_core.scripts.probe_book --corpus      # every *.pdf in CORPUS_DIR
  Exit 0 if all OK, 1 if any book is scanned/empty (do not index it).
  """
  import argparse, sys
  from pathlib import Path
  from neuro_core.config import load_config
  from neuro_core.ingest import probe_book

  def _fmt(r):
      flag = "OK  " if r["ok"] else "SKIP"
      return (f"[{flag}] {r['book']}: {r['pages']}p text={r['coverage']:.2f} "
              f"chapters={r['chapters']} figpages={r['pages_with_figures']} — {r['reason']}")

  def main(argv=None):
      ap = argparse.ArgumentParser(prog="probe_book")
      ap.add_argument("pdf", nargs="?", help="PDF path to probe")
      ap.add_argument("--corpus", action="store_true", help="probe every *.pdf in CORPUS_DIR")
      args = ap.parse_args(argv)
      if args.corpus:
          paths = sorted(load_config().corpus_dir.glob("*.pdf"))
      elif args.pdf:
          paths = [Path(args.pdf)]
      else:
          ap.error("give a PDF path or --corpus")
      all_ok = True
      for p in paths:
          r = probe_book(p)
          print(_fmt(r))
          all_ok = all_ok and r["ok"]
      return 0 if all_ok else 1

  if __name__ == "__main__":
      sys.exit(main())
  ```

  Test (`tests/neuro_core/test_probe_book_script.py`):
  ```python
  from neuro_core.scripts.probe_book import main

  def test_script_ok_on_tiny_pdf(tiny_pdf, capsys):
      rc = main([str(tiny_pdf)])
      out = capsys.readouterr().out
      assert rc == 0
      assert "OK" in out and "Sample Book" in out

  def test_script_requires_arg(capsys):
      import pytest
      with pytest.raises(SystemExit):
          main([])
  ```
  Verify: `.loopvenv/bin/python -m pytest -q tests/neuro_core/test_probe_book_script.py` → pass.
  Commit: `feat(scripts): add probe_book CLI for corpus preflight`.

- [x] **Task 3 — Repo runbook `docs/runbooks/integrating-a-textbook.md` + import-consistency test**

  **Files:** Create `docs/runbooks/integrating-a-textbook.md`; Test
  `tests/neuro_core/test_runbook_consistency.py` (new).

  Write the runbook (neuro-caseboard-specific, derived from the `integrating-a-textbook` skill):
  active dirs and the `CORPUS_DIR` export; **Step 1 probe** (`python -m neuro_core.scripts.probe_book
  --corpus`); **Step 2 stage** PDF into `CORPUS_DIR` + byte-verify; **Step 3 text index**
  `CORPUS_DIR=/home/michael/textbook_pdfs python -m neuro_core.scripts.build_index`; **Step 4 visual
  lane STANDALONE** `... python -m neuro_core.scripts.build_visual_index` with the OOM-gotcha
  callout (the in-process build inside `build_index` can be SIGKILLed silently, leaving `figures`
  stale); **Step 5 verify both tables** with `to_arrow()` (not `to_pandas`); **Step 6 validate**
  (`pytest`, `eval.run_eval`, `eval.figure_eval`, one real in-domain query); **Step 7 go live**
  (restart the server — it caches the index at startup). Note the heavy build needs the system
  Python (torch+CUDA+models), not the hermetic loop venv.

  Test (`tests/neuro_core/test_runbook_consistency.py`) — guards that the runbook's commands stay
  real as code evolves:
  ```python
  import importlib, pathlib

  def test_runbook_referenced_modules_import():
      for m in ("neuro_core.scripts.probe_book", "neuro_core.scripts.build_index",
                "neuro_core.scripts.build_visual_index"):
          importlib.import_module(m)

  def test_runbook_mentions_key_steps():
      doc = pathlib.Path("docs/runbooks/integrating-a-textbook.md").read_text()
      for token in ("probe_book", "build_index", "build_visual_index", "CORPUS_DIR", "to_arrow"):
          assert token in doc, token
  ```
  Verify: `.loopvenv/bin/python -m pytest -q tests/neuro_core/test_runbook_consistency.py` → pass.
  Commit: `docs(runbook): add neuro-caseboard textbook integration runbook + consistency test`.

- [x] **Task 4 — Run-log `docs/runbooks/2026-06-18-practical-neuroangiography.md`**

  **Files:** Create `docs/runbooks/2026-06-18-practical-neuroangiography.md`.

  Honest record of THIS integration. Include: the verified probe evidence (coverage 0.989, 525
  pages, 519 with text, 40 chapters, 381 figure-pages); confirmation the PDF is already staged in
  the active `CORPUS_DIR`; the exact runtime build commands (with `CORPUS_DIR` export) to run on the
  GPU host; a "Results — fill after the runtime build" section with placeholders for the `chunks`
  and `figures` table counts and the real-query citation check; and an explicit note that the
  live-index build is human-gated (not run by the loop). No test (pure evidence doc).
  Commit: `docs(runbook): add Practical Neuroangiography integration run-log`.

## Non-goals (explicit — do NOT do these in the loop)

- Running `build_index` / `build_visual_index` (mutates the live LanceDB index the web app serves;
  GPU + `models` extra required). Documented in the run-log for the user to run, or for the loop to
  offer at the READY gate.
- Editing eval gate YAML or adding eval cases that can only run against the live index (the gates
  are tuned to the existing corpus; the skill warns against gaming them).
- Adding a stem→title citation registry (the project intentionally has none; citations derive from
  the filename stem + PDF bookmarks).
- Any change to existing index/build behavior for books that already index cleanly.
