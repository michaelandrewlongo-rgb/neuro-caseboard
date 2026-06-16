# Design — WS-5: Case PDF surface + `caseboard case` CLI + Streamlit Case lane

- **Date:** 2026-06-16
- **Status:** Implemented
- **Branch:** `worktree-streamlit-executive-navy-loop`
- **Loop:** Case Dossier engine, Pass 5 of 5 · builds on WS-1..WS-4

## 1. Context & problem
WS-1..WS-4 produce a case `Dossier` (8 sections + `[L#]` literature + generated schematics). WS-5
ships the **surface**: a print-grade PDF, a `caseboard case` CLI, and a Streamlit "Case" lane — with
a standing confidentiality/verify banner on every page, and the offline fpdf2 fallback kept so the
required CI smoke passes without Chromium.

## 2. Decisions
- **Reuse the renderers.** The case `Dossier` is the same model the build path renders, so
  `render_case_pdf` (Executive-Navy `caseboard_pdf` → Chromium, with the `render_pdf` fpdf2 fallback)
  already lays out sections/claims/figures. WS-5 adds two things to *both* renderers: the per-section
  `[L#]` literature block, and the per-page verify banner.
- **Verify banner on every page.** fpdf2: an `FPDF.footer()` subclass (`_CaseboardPDF`) draws it on
  every page (auto-break margin widened to 20mm). Exec/Chromium: a `position:fixed` banner div that
  Chromium repeats per printed page. Applied to *all* dossier PDFs (build + case), per §6.
- **`generate_case(dictation, …)`** mirrors `generate`: parse → `build_case_dossier(figures_dir=out)`
  → write `case-dossier.md` (+ `.pdf`); `use_llm=False` forces deterministic intake + authors.
- **CLI `caseboard case`** with `--pdf/--no-llm/--no-enrich/--no-literature/-o`; prints
  `missing_critical()` as a non-blocking note.
- **Streamlit "Case" lane**: a dictation textarea → dossier + schematics + PDF download, mirroring the
  Build lane; verified by the syntax/byte-compile gate (no AppTest harness exists).

## 3. Acceptance (LOOP_PROMPT §5 WS-5) — all met
- `caseboard case "<dictation>" --pdf` produces a PDF with all eight sections + figures. ✓ (offline
  smoke: 8 sections, 2 schematics, 5-page PDF).
- The offline `--no-llm` smoke passes in CI without Chromium (clinical fpdf2 path). ✓
- Every page carries the verify banner. ✓ (5/5 pages, asserted via pymupdf).
- No broken glyphs (embedded Unicode font + ASCII fallback). ✓
- No new runtime dependency; `caseboard` entry point imports on core deps. ✓

## 4. Testing
`test_caseboard_pdf.py` (+2: banner present + position:fixed; section `[L#]` block);
`test_render_pdf.py` (+2: verify banner on every page via pymupdf; section `[L#]` in the PDF);
`test_cli.py` (+1: `case --pdf --no-llm --no-literature` writes md with 8 sections + a `%PDF`);
syntax gate over `app/` covers the Streamlit lane. 449 passed, 0 regressions.

## 5. Out of scope / deferred
Live blind judges (text-quality, PubMed recency, image ≥8/10) — need a configured provider/visual
judge, absent here; offline harnesses render the artifacts for a keyed run.
