# WS-5: Case PDF surface + `caseboard case` CLI + Streamlit Case lane — Plan

**Goal:** Ship the case surface: a print-grade PDF (per-page verify banner + `[L#]` literature),
`caseboard case` CLI, and a Streamlit Case lane. Offline fpdf2 fallback keeps required CI green.

**Spec:** `docs/superpowers/specs/2026-06-16-ws5-case-pdf-cli-streamlit-design.md`

---

## Task 1: PDF renderers (test-first)
- `render_pdf.py`: `_CaseboardPDF(FPDF)` with a per-page `footer()` verify banner; `_render_literature`.
- `caseboard_pdf.py`: `position:fixed` verify banner + `_literature_html` per section.
- Tests: `test_caseboard_pdf.py` (+2), `test_render_pdf.py` (+2, banner on every page via pymupdf).

## Task 2: `generate_case` + CLI (test-first)
- `pipeline.generate_case(dictation, …)`; `cli` `case` subparser + `_run_case`.
- Test: `test_cli.py` (+1) — `case --pdf --no-llm --no-literature` writes md (8 sections) + `%PDF`.

## Task 3: Streamlit Case lane
- `app/streamlit_app.py`: "Case" mode (dictation → dossier + schematics + PDF). Verify via byte-compile.

## Task 4: Verify + record
- Syntax gate (`compileall`), full suite, import gate + entry-point `case` help. Append Pass-5 line +
  LOOP COMPLETE to `LOOP_LOG.md`; commit.
