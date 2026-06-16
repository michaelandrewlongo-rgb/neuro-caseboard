# Design — Executive-Navy PDF export for the Ask pathway

- **Date:** 2026-06-16
- **Status:** Approved (design); implementation pending
- **Branch:** `worktree-ask-pdf-export-pr7-design` (off `master` @ PR #7 merge `25c7f8d`)

## 1. Context

PR #7 ("Executive-Navy console redesign + design-matched case-board PDF") introduced a new
print identity — a deep-navy masthead over a bright report plane, a three-font role system
(Archivo UI / Source Serif 4 reading column / IBM Plex Mono micro-labels), one deep-teal
accent — and applied it to the **build** pathway via `neuro_caseboard/caseboard_pdf.py`
(renders a `Dossier`). `pipeline.render_case_pdf()` is its single source of truth, wired into
both `caseboard build --pdf` and the Streamlit Build lane, with an offline fpdf2 fallback
(`render_pdf.py`) gated by `CASEBOARD_PDF_STYLE`.

The **ask** pathway has no live PDF export. `neuro_caseboard/briefing_pdf.py` exists but:

- renders the **superseded** dark "Signal v1" design (Syne/Inter, teal `#22d3ee` / red
  `#ef4444` glow), not Executive-Navy; and
- is **orphaned** — referenced only by its own tests and the optional-integration CI job,
  not by any CLI command or the Streamlit app.

## 2. Goal

Let `ask` (Q&A) responses be exported as a PDF in the **Executive-Navy** identity — the print
sibling of `caseboard_pdf.py`, but walking the `QAResult` shape instead of a `Dossier`.

### Non-goals (YAGNI)
- No new visual design — we replicate PR #7's Executive-Navy exactly.
- No PDF for the Cards lane.
- No changes to retrieval / answer synthesis logic.
- No PDF for the `Clarification` path (an ambiguous query has no answer to render).

## 3. Decisions (confirmed with the user)

1. **Surfaces:** expose on **both** `caseboard ask --pdf` (CLI) and a Streamlit Ask-lane
   download button.
2. **Offline behavior:** provide an **fpdf2 offline fallback** so `ask --pdf` always produces a
   PDF even with no Chromium (mirrors build; keeps the required offline CI gate green).
3. **Old design:** **replace** the orphaned Signal `briefing_pdf.py` with the Executive-Navy
   design (one identity across the product); update its tests.
4. **Structure (approved):** two small **behavior-preserving extractions** so the brand lives
   in one place — `exec_navy.py` (shared print CSS + helpers) and `fpdf_base.py` (shared fpdf2
   font setup) — rather than duplicating tokens across files.

## 4. Data shape (`QAResult`, from `qa.py`)

```
QAResult:
  answer:     str                      # markdown
  citations:  list[ {n, book, chapter, page} ]
  figures:    list[ {source_n, book, page, image_path, caption} ]
  literature: LiteratureSection | None # { narrative: str(markdown),
                                         #   citations: [ {n, pmid, title, journal, year, doi, url} ] }
```

`answer_question()` may instead return a `neuro_core.query.Clarification` (no answer) — callers
already special-case it; the PDF path must be skipped for it.

Field access stays **duck-typed** (the existing `_g(obj, key)` reads dict-or-attribute) so
tests can pass dicts and the engine can pass dataclasses, exactly as today.

## 5. Architecture — module map (symmetric with the build side)

| Concern | Build (exists) | Ask (this work) |
|---|---|---|
| Exec-Navy HTML→PDF | `caseboard_pdf.py` | `briefing_pdf.py` (rewrite Signal→Exec-Navy) |
| Offline fpdf2 fallback | `render_pdf.py` | fpdf2 Q&A renderer (new, in `briefing_pdf.py`) |
| Single source of truth | `pipeline.render_case_pdf()` | `pipeline.render_ask_pdf()` (new) |
| Shared print theme | inline in `caseboard_pdf.py` | `exec_navy.py` (extract → both import) |
| Shared fpdf2 font setup | inline in `render_pdf.py` | `fpdf_base.py` (extract → both import) |

### 5.1 `exec_navy.py` (new) — shared print theme
- `BASE_CSS`: the shared Executive-Navy token block + components used by *both* renderers:
  `@import` fonts, `:root` tokens, `@page`, `body`, `.masthead`, `.mh-*`, `.eyebrow`,
  `h1.title`, `.standfirst`, `.rule`, `.section`/`.sec-h`/`.sec-intro`, `figure`/`figcaption`,
  `.footer`.
- `inline(text)`: HTML-escape then promote `**bold**` → `<b>`.
- `img_data_uri(path)`: basename-derived MIME → base64 data URI (the PR #7 robust version).

`caseboard_pdf.py` is refactored to `EXEC_NAVY_CSS = exec_navy.BASE_CSS + _BUILD_COMPONENTS_CSS`
(its build-only classes — `.evbar`, `.metric(s)`, `.legend`, `.claim`, `.marker`, `.why`,
`.subs`, `.xnote`, `.appendix`) and to call `exec_navy.inline` / `exec_navy.img_data_uri`.
**Behavior-preserving**: verified by `caseboard_pdf` HTML token/content asserts (add a focused
test if none exists) plus the existing offline test suite.

### 5.2 `briefing_pdf.py` (rewrite) — Q&A Exec-Navy renderer + fpdf2 fallback
Keep the public API and the content logic; swap the design.

- `build_briefing_html(result, *, title, subtitle="", eyebrow="Ask · Citation-grounded",
  today=None) -> str` — **pure** (no Chromium). Composes `exec_navy.BASE_CSS +
  _ASK_COMPONENTS_CSS`. Retains `_md_to_html` (answer/narrative markdown → HTML), duck-typed
  `_g`, `_literature_html`, and robust figure skipping (unreadable image → caption-only, never
  a broken `<figure>`). Emits the Exec-Navy structure (see §7).
- `render_briefing_pdf(result, out_path, *, title, subtitle="", eyebrow=...) -> str` —
  Playwright/Chromium render (unchanged skeleton: `set_content` → `document.fonts.ready` →
  `page.pdf(A4, print_background, zero margins)`). Needs the `briefing` extra.
- `render_briefing_clinical_pdf(result, out_path, *, title, subtitle="") -> str` — **new**
  offline fpdf2 renderer for the `QAResult` shape. Uses `fpdf_base` for font registration +
  ASCII fallback. Layout: title (the question) → the answer (minimal markdown: `##`/`###`
  headings as bold lines, `-`/`*` bullets, paragraphs via `multi_cell`; inline `**bold**` may
  be flattened to plain text — acceptable for the degraded offline path) → "Sources" list
  (`[n] book, chapter, p.page`) → "Contemporary Literature" (narrative + `[L#]` entries) →
  figures (image if readable + caption). Pure-Python, no network, no Chromium.

### 5.3 `fpdf_base.py` (new) — shared fpdf2 font setup
Extract `_register(pdf) -> (family, is_unicode)`, `_ascii(s)`, and `_REPL` from `render_pdf.py`
verbatim. `render_pdf.py` imports them (behavior-preserving; covered by `test_render_pdf.py`);
the new clinical Q&A renderer imports them too.

### 5.4 `pipeline.render_ask_pdf(result, question, path)` (new) — single source of truth
Analogous to `render_case_pdf`:

```python
def render_ask_pdf(result, question, path):
    style = os.environ.get("CASEBOARD_PDF_STYLE", "exec").strip().lower()
    if style != "clinical":
        try:
            from neuro_caseboard.briefing_pdf import render_briefing_pdf
            render_briefing_pdf(result, path, title=question)
            return Path(path)
        except Exception as e:
            if not _exec_renderer_unavailable(e):
                raise          # real bug → surface it, never a silently-degraded PDF
            logging.warning("Exec-Navy ask PDF renderer unavailable (%r); using fpdf2 fallback.", e)
    from neuro_caseboard.briefing_pdf import render_briefing_clinical_pdf
    render_briefing_clinical_pdf(result, path, title=question)
    return Path(path)
```

Reuses the existing `_exec_renderer_unavailable` (ImportError or `playwright.*` only) and the
`CASEBOARD_PDF_STYLE` env var. Title = the question.

## 6. Wiring

### 6.1 CLI (`cli.py`)
- `ask` subparser gains `--pdf` (flag) and `-o`/`--output` (path; default `ask-<slug>.pdf` via
  the existing `_slug`).
- In `_run_ask`: after the existing stdout print, if `args.pdf` and the result is a real
  `QAResult` (not `Clarification`, GPU guard passed), call
  `render_ask_pdf(result, args.question, out_path)` and print `Wrote <path>`. Clarification and
  GPU-not-ready paths return early as today (no PDF).

### 6.2 Streamlit Ask lane (`app/streamlit_app.py`)
- After the Sources / Contemporary-Literature sections, add a **"Prepare PDF"** checkbox
  (default off, so Chromium stays off the hot path — Ask answers render eagerly on every
  keystroke-run, unlike Build which is button-gated). When checked: render to a temp file via
  `render_ask_pdf(result, q, …)`, read bytes, show `st.download_button("Download PDF", …,
  file_name="ask-<slug>.pdf")`. Only reachable for real answers (already past the
  `Clarification` `st.stop()`).

## 7. Design fidelity — Q&A content → Exec-Navy structure

Same masthead (`NEURO·CASEBOARD` + eyebrow `Neurosurgery Signal · clinical briefing`),
`Ask · Citation-grounded` eyebrow chip, `h1.title` = the question, optional `.standfirst`,
`.rule`, Exec-Navy section headers, figure cards, footer, and the three-font system.

Q&A-specific mapping:
- **Answer** → Source Serif reading column (`_md_to_html`, with `**bold**`).
- **Sources** → an Exec-Navy `.section` header + source rows (`[n] book, chapter, p.page`).
- **Contemporary Literature** → its own `.section` with the narrative + `[L#]` citation rows
  (journal, year, DOI/URL link), rendered only when present.
- **Figures** → Exec-Navy `figure`/`figcaption` cards; unreadable images dropped, never broken.

Build-only chrome (evidence-mix bar, status-marker claim cards, appendix) is intentionally
omitted — the ask result carries no evidence-status summary.

## 8. Testing plan

Offline-first (everything below runs in the required `ci.yml` gate; no Chromium):

- **Rewrite** `test_briefing_pdf.py` + `test_briefing_literature.py`: swap Signal token asserts
  (Syne, `#22d3ee`, `#ef4444`, `.dot`) for Exec-Navy asserts (Archivo / Source Serif 4 / IBM
  Plex Mono, accent `#0e7490`, `.masthead`, `Ask · Citation-grounded`). **Keep** all content
  asserts (title, `Greenberg, Trauma, p.1102`, `<b>`/bold, dict-shaped result, the
  "Assuming…" bold line, literature present/absent).
- **New** `render_briefing_clinical_pdf` test: emits a real `%PDF` (`data[:5] == b"%PDF"`,
  non-trivial size), purely offline, including the no-figure and unreadable-figure cases.
- **New** `render_ask_pdf` orchestration tests: `CASEBOARD_PDF_STYLE=clinical` → fpdf2 path;
  default with a monkeypatched exec renderer raising `ImportError` → falls back; a generic
  exception → re-raised (not masked).
- **New** CLI test (extend `test_cli.py`): monkeypatch `_answer_question` to return a fake
  `QAResult`; `ask --pdf -o <tmp>` under `CASEBOARD_PDF_STYLE=clinical` writes the file;
  a `Clarification` result writes no PDF.
- **Optional** light Streamlit `AppTest` for the Ask lane PDF control (none exists today; add
  only if cheap and stable — otherwise rely on manual verification + the CLI/orchestrator
  tests).
- Re-confirm the build side is unchanged: existing `test_pipeline.py` / `test_render_pdf.py`
  stay green after the `exec_navy.py` / `fpdf_base.py` extractions.

## 9. CI

- **`ci.yml` (required, offline):** unchanged shape; the new offline tests run here. The syntax
  gate already byte-compiles `app/`, so `streamlit_app.py` edits must stay importable.
- **`optional-integration.yml` (manual/weekly):** the existing `briefing-pdf` job already
  renders a Q&A-shaped result through `render_briefing_pdf` end-to-end via Chromium — it stays
  and continues to pass (re-label its comment/title from "Signal-styled" to "Executive-Navy").

## 10. Risks & mitigations

- **Refactoring the working build renderer** (`caseboard_pdf.py`/`render_pdf.py`): kept
  behavior-preserving (pure string composition / verbatim helper move) and guarded by the
  existing offline suite plus a focused build-HTML token test.
- **fpdf2 markdown fidelity:** the clinical fallback flattens rich inline formatting; this is
  the documented degraded offline path, consistent with `render_pdf.py`'s existing posture.
- **Ask-lane latency:** the "Prepare PDF" checkbox keeps Chromium off the default render path.

## 11. Implementation order (for the plan)

1. `fpdf_base.py` extraction + `render_pdf.py` import swap (verify build clinical PDF).
2. `exec_navy.py` extraction + `caseboard_pdf.py` import swap (verify build exec PDF).
3. `briefing_pdf.py` rewrite: Exec-Navy `build_briefing_html`/`render_briefing_pdf` +
   `render_briefing_clinical_pdf`; rewrite the two briefing tests.
4. `pipeline.render_ask_pdf` + orchestration tests.
5. CLI `ask --pdf`/`-o` + CLI test.
6. Streamlit Ask-lane "Prepare PDF" + download.
7. Re-label the optional-integration job comment.
8. Full offline suite green; manual Chromium spot-check of one ask PDF.
