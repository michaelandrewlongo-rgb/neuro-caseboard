# Phase 1 — Unified surface (one CLI + one web app)

**Date:** 2026-06-14
**Status:** Approved design (this spec implements Phase 1 of the integration; Phase 0 is merged)
**Author:** Michael Longo + Claude
**Predecessor:** `2026-06-14-caseboard-textbookrag-integration-design.md` (§4 Phase 1)

## 1. Context & problem

Phase 0 unified the engine: both Q&A and board generation now run over a single importable
`neuro_core` with one figure lane. What remains split is the **user surface**:

- **Two CLIs.** `caseboard build "<topic>"` (console script `caseboard` → `neuro_caseboard.cli`)
  and a separate Q&A CLI run as `python -m qa.cli.ask "<question>"`.
- **Two web surfaces for Q&A — and none for boards.** Q&A ships *both* a FastAPI app
  (`qa/server/`: `POST /ask`, `/login`, `/figures/{name}`, static JS viewer at `/`) *and* a
  Streamlit app (`qa/app/streamlit_app.py`). Board generation has **no** web surface at all — it
  only produces `case-board.md`/`.pdf` files on disk.

This is the duplication the integration is meant to remove: a user cannot ask a question and build
a board from one place, and the Q&A surface itself is built twice.

## 2. Decisions (locked during brainstorming)

- **Audience: local, single-user.** No real auth, no accounts, no durable job queue. Board
  generation runs **in-process** with a progress indicator.
- **Stack: Streamlit is the single web app.** Rationale: content quality lives entirely in
  `neuro_core` + the board pipeline (none of it in the web layer), so the only thing the stack
  choice changes is how many cycles go to UI plumbing. Streamlit minimizes that plumbing (the Q&A
  app already exists; long board runs map naturally to a spinner). The FastAPI + static-JS path is
  retired.
- **Scope: thin, pure-plumbing.** Phase 1 unifies surfaces and removes duplication. **No**
  retrieval/synthesis/board-content changes — content quality is a separate, dedicated effort.
- **The static JS viewer is deleted** (git history preserves it), along with the FastAPI server it
  depended on.

## 3. Detailed design

### 3.1 One CLI — extend the `caseboard` binary

`neuro_caseboard/cli.py` gains an `ask` subcommand beside the existing `build`:

- `caseboard ask "<question>" [--force]` → prints the answer, then `Sources:` (numbered
  book/chapter/page citations), then `Figures:` (source-n, book, page, image path) — exact parity
  with today's `qa/cli/ask.py`. It calls `neuro_core.query.query(question, force=...)` and maps
  `GpuNotReadyError` to a stderr message + exit 1, identical to the current behavior.
- `caseboard build "<topic>" [-o/--pdf/--no-enrich/--no-llm]` → unchanged.

`qa/cli/` is then deleted. The `ask` handler logic is small and lives directly in `cli.py`
(same shape as the existing `build` branch), so no new module is needed.

### 3.2 One web app — a single Streamlit app, two modes

A top-level **`app/streamlit_app.py`** (moved out of `qa/app/` because the app now spans both
features, so the `qa` name no longer fits). A sidebar mode toggle (`st.sidebar.radio`) selects:

- **Ask** — today's Streamlit Q&A behavior, unchanged: question input → `neuro_core.query.query`
  → render answer + figures.
- **Build board** — topic text input + option checkboxes (PDF, enrich, use-LLM) + a button →
  `st.spinner("Building board…")` while `neuro_caseboard.pipeline.build_dossier(topic, enrich=…,
  use_llm=…)` runs **in-process** → render the result (see presenter below). A
  `st.download_button` offers the PDF, produced on demand (§3.2.1).

Auth: keep the existing optional `APP_PASSWORD` gate (no gate when the env var is unset, i.e.
locally). The vestigial `sys.path.insert(...)` + its stale "make `engine` importable" comment are
removed.

#### 3.2.1 Board-view presenter (the one piece of real logic, made testable)

`build_dossier()` returns an in-memory `Dossier` (no disk write). Its
`sections[].figures[]` are `FigureItem(image_path, caption, citation, …)` and `summary` is an
`EvidenceSummary(supported, to_verify, quarantined)` — everything the view needs is already in
memory, so **no disk scanning**.

To keep the Streamlit script near-logic-free and unit-testable without a browser, extract a pure
helper in a new module **`neuro_caseboard/board_view.py`**:

```
@dataclass
class BoardView:
    title: str
    markdown: str                      # board prose/structure as markdown (from render_md)
    figures: list[FigureItem]          # flattened from dossier.sections[].figures, de-duped by image_path
    summary: EvidenceSummary           # supported / to_verify / quarantined counts

def board_view(dossier: Dossier) -> BoardView: ...
```

`board_view` flattens the section figures (de-duping by `image_path`, preserving first-seen order)
and reuses the existing `neuro_caseboard.render_md` for the markdown body. The Streamlit Build
branch then: `st.markdown(view.markdown)`, a `st.image` per `view.figures` (with caption +
citation), and a small counts line from `view.summary`. Rendering figures explicitly via
`st.image` (rather than relying on `st.markdown` to resolve local image paths) is what makes them
display reliably.

PDF for download is produced on demand by calling the existing `neuro_caseboard.render_pdf` into a
temp file and reading its bytes — only when the user has the PDF option enabled — so the Build view
never depends on a user-chosen output directory.

### 3.3 Retire the duplicate surface

- Delete `qa/server/` (`main.py`, `auth.py`, `schemas.py`) and `qa/web/` (`index.html`,
  `app.js`). Nothing external imports or deploys them (no console script, no Dockerfile/Procfile/
  CI reference).
- Delete the corresponding tests: `tests/neuro_core/test_server.py`,
  `tests/neuro_core/test_auth.py`. (The merged suite drops by exactly these tests; nothing else
  changes.)
- After `qa/cli` (§3.1), `qa/server`, and `qa/app` are gone, the `qa/` package is empty — remove
  it entirely.

### 3.4 Packaging + docs

- `pyproject.toml`: `packages.find` include becomes `["neuro_caseboard*", "neuro_core*"]` (drop
  `qa*`). `app/` is a `streamlit run` script, not an installed package, so it needs no packaging
  entry.
- `README.md`: document the three entry points — `caseboard ask "<q>"`, `caseboard build
  "<topic>"`, and `streamlit run app/streamlit_app.py` (with the optional `APP_PASSWORD` note).

## 4. Acceptance criteria

- `caseboard ask "<q>"` prints answer + numbered citations + figures, byte-for-byte equivalent to
  the old `python -m qa.cli.ask "<q>"` for the same query (parity).
- `caseboard build "<topic>"` is unchanged (existing build tests still pass).
- `streamlit run app/streamlit_app.py` launches a single app with Ask and Build modes; Build
  renders board markdown + figures and offers a PDF download.
- Static checks: no `qa/` package remains; no FastAPI/`uvicorn` import remains in the tree; exactly
  one web app; one CLI binary with two subcommands.
- The merged suite is green, equal to the Phase 0 baseline (290) minus the intentionally removed
  `test_server.py` + `test_auth.py`, plus the new `ask`-dispatch and `board_view` tests.

## 5. Testing strategy

- **CLI:** test that `caseboard ask` dispatches to `query` and renders the answer/citations/figures
  block, and that `GpuNotReadyError` → exit 1 on stderr (mirror the parity assertions; the
  underlying `query()` is already covered in `neuro_core` tests). The existing `build` dispatch
  test stays.
- **Presenter:** unit-test `board_view(dossier)` on a hand-built `Dossier` — figure flattening +
  de-dup by `image_path` + order preservation, markdown delegation, and summary pass-through. This
  is where the Build-mode logic is verified; the Streamlit `.py` stays a thin view with no testable
  logic of its own.
- **No browser/UI tests** for the Streamlit script (out of scope; the logic lives in the
  presenter).
- Remove `test_server.py` / `test_auth.py` with the server. Run the full suite; confirm the count
  matches §4.

## 6. Risks & mitigations

- **`ask` parity drift** — the CLI output format must match the old Q&A CLI exactly. Mitigate by
  porting the print block verbatim and asserting on it in a test.
- **Streamlit can't render local figure paths via markdown** — mitigated by rendering figures
  explicitly with `st.image` from the in-memory `FigureItem`s (§3.2.1), not via markdown image
  links.
- **Long board run blocks the Streamlit thread** — acceptable for single-user local (the spinner
  covers it); the in-process model is an explicit Phase 1 decision, not an oversight. A durable job
  model is deferred to if/when the audience changes.
- **Hidden importer of `qa.server`/`qa.web`** — verified none exists (grep across py/md/toml/
  Dockerfile/Procfile/yaml). The removal is safe.

## 7. Out of scope (Phase 1)

- Cross-feature flows (board card → "ask a follow-up"; answer → "build a board"; a shared evidence
  model reconciling `neuro_core` `Hit`/`Citation` with caseprep `EvidenceRecord`) — **Phase 2**.
- Any content/retrieval/synthesis/board-pipeline quality change — separate dedicated effort.
- Multi-user auth, accounts, durable job queue, remote deploy — only if the audience changes.
- Restyling Streamlit or reviving the JS viewer's look — a later design pass.
- Renaming the product/repo.

## 8. Resolved decisions

- Audience: **local, single-user**; boards generate **in-process** with a spinner.
- Web stack: **Streamlit**, single app, two modes; FastAPI server + static JS viewer **deleted**.
- Scope: **thin, pure-plumbing**; content quality handled separately.
- CLI: extend the existing **`caseboard`** binary with `ask` (no new console script).
- App location: top-level **`app/streamlit_app.py`**; `qa/` package dissolved.
