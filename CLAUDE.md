# CLAUDE.md — Neuro·Caseboard

Project-specific gotchas that are **not derivable from the code**. Generic workflow discipline
(TDD-first, verify-before-claiming-done) is already enforced by the superpowers skills, so this file
captures only what those skills can't know about this repo and this machine.

## Architecture at a glance

One engine assembled from **three layers**; read these together to understand any change:

- **`caseprep/`** (vendored at `vendor/caseprep/caseprep`) — the audited
  `Explorer → Enricher → Auditor` pipeline that turns a free-text case into a validated
  `AuditedManifest` of operative question-cards. Reused as a library.
- **`neuro_core/`** (formerly the textbook-rag repo) — the citation-grounded **retrieval +
  figure engine**: LanceDB hybrid search over textbook chunks (`index.py`, `query.py`,
  `chunk.py`, `embed.py`, `rerank.py`), a separate figure/visual lane
  (`figure_retriever.py`, `visual_index.py`, `figure_guards.py`), the standalone board-review
  `cards` lane (`cards_*.py`), and synthesis clients (`synth_clients.py`, `synthesize.py` —
  OpenRouter `glm-5.2` by default, Vertex/Gemini alternate; see runtime note below).
- **`neuro_caseboard/`** — orchestration + the **rebuilt report/export surface** that owns the
  data model and renderers (`model.py` → `compile.py` → `render_md.py` / `render_pdf.py`),
  plus the PubMed literature lane (`literature/`, `case_literature.py`), the citation
  **entailment gate** (`entailment.py`), woven synthesis (`woven_synth.py`), and the
  LLM-first Explorer (`explore_llm.py`) with the deterministic anti-bleed `guard.py`.

**Two pathways** (both routed through `pipeline.py` / `cli.py`):
- **Ask** (`caseboard ask`): question → `neuro_core` retrieval (chunks + figures) → synthesis →
  cited answer, augmented with a PubMed "Contemporary Literature" `[L#]` section; every corpus
  citation must pass `entailment.py` or the claim is downgraded to *needs-verification*.
- **Build / Case** (`caseboard build` / `case`): free-text case → caseprep Explorer (LLM-first,
  deterministic fallback) → Enricher → Auditor → `compile.py` (manifest + evidence → `Dossier`)
  → Markdown/PDF.

**Surfaces over the same engine:** the `caseboard` CLI; a React SPA (`web/`) over a FastAPI
wrapper (`api/server.py`); a legacy Streamlit app (`app/streamlit_app.py`); and a Signal-styled
briefing PDF (`neuro_caseboard/briefing_pdf.py`).

## Common commands

```bash
pip install -e .[dev]                       # the ONLY supported install (see Install & packaging)

# CLI (entry point: neuro_caseboard.cli:main)
caseboard ask "what supplies Wernicke's area?"
caseboard build "C5-6 corpectomy" --pdf -o out/   # dossier; --no-llm forces deterministic Explorer
caseboard case "<free-text dictation>"            # patient-specific dossier
caseboard cards "cavernous sinus"                 # search the board-review card bank

# Web / dev
./dev.sh                                    # React SPA (Vite :5173) + FastAPI engine (:8001) together
streamlit run app/streamlit_app.py          # legacy single-app UI (needs the `web` extra)
scripts/serve-phone.sh                       # SPA+API on 0.0.0.0:8001 for phone access (see Web console)
cd web && npm run lint && npm run test       # eslint + vitest for the SPA (NOT a Python-CI gate)

# Tests (read the Testing section before running — full suite is ~17 min here)
pytest tests/neuro_core tests/test_pipeline.py tests/test_retrieve.py tests/test_qa.py  # fast scoped loop
pytest tests/test_qa.py::test_<name>         # a single test
ci/local-ci.sh                               # reproduce the full REQUIRED CI in a throwaway venv

# Build the corpus index / card bank (needs the live data paths below)
python -m neuro_core.scripts.build_index         # textbook chunk + figure index
python -m neuro_core.scripts.build_cards_index   # board-review cards table
python -m build                                  # build sdist + wheel (matches the `package` CI job)
```

## Environment & runtime (this machine)

- **Default Ask synthesis is OpenRouter `glm-5.2`; Vertex Gemini is the alternate (PR #80).**
  `SYNTH_PROVIDER=openrouter` + `OPENROUTER_MODEL=z-ai/glm-5.2` is the default (best blind-graded
  answer quality), and query **disambiguation runs a separate fast model**,
  `ANALYZE_MODEL=google/gemini-3.1-flash-lite` (empty `ANALYZE_MODEL` reuses the synth client).
  This needs `OPENROUTER_API_KEY` (kept in `.env`). To revert Ask synthesis to free Vertex Gemini,
  set `SYNTH_PROVIDER=vertex` (+ `VERTEX_MODEL=gemini-2.5-pro`).
- **Vertex is still required for Build + briefing even on the OpenRouter synth default.** The
  Build/Case **Explorer** is independent, selected by `CASEBOARD_LLM_PROVIDER` (`vertex` default
  on this machine), and the operative-briefing per-section calls stay on Vertex Gemini-Flash
  whenever `GOOGLE_CLOUD_PROJECT` is set. So keep `GOOGLE_CLOUD_PROJECT` + ADC at
  `~/.config/gcloud/application_default_credentials.json` (+ `google-genai`); probe both Vertex
  (ADC) and OpenRouter (`OPENROUTER_API_KEY`) in any health check. `neuro_core/config.py` defaults
  now match this (no longer stale). On this machine the old `SYNTH_PROVIDER=vertex` export in
  `~/.bashrc` is commented out — a fresh shell / restarted session picks up the glm-5.2 default.
- **Live data paths live outside the repo** (so git worktrees share them automatically — no symlinks):
  - Corpus PDFs: `/home/michael/textbook_pdfs` (set `CORPUS_DIR`; the `/mnt/d/...` default is stale).
  - LanceDB index + figure assets: `/home/michael/neuro-textbook-rag/index` and `.../assets/figures`.
  - Cards table is live **inside** `INDEX_DIR/cards.lance`; a missing `CARDS_SOURCE_DB` does **not**
    disable cards (it's only the source deck used to build the table).
- **`.env` at repo root** is gitignored and auto-loaded by
  `neuro_caseboard/literature/config.py::_load_dotenv_once()` (dependency-free; real env vars win).
  Holds `NCBI_API_KEY`. Tests opt out via `NEURO_CASEBOARD_SKIP_DOTENV=1` (set in `tests/conftest.py`).

## Install & packaging

- **`caseprep` is vendored in-tree** at `vendor/caseprep/caseprep` (setuptools `package-dir` maps it to
  the `caseprep` import name). Install **`pip install -e .[dev]` only**.
- **Never `pip install -e ../caseprep`.** A stale external copy at `/home/michael/PROJECTS/caseprep`
  shadows the vendored one and breaks imports like
  `from caseprep.audit.card_auditor import accepted_papers`.

## Testing (read before running pytest)

- **CI is pytest only.** `.github/workflows/ci.yml` runs `python -m pytest` over
  `testpaths = ["tests", "vendor/caseprep/tests"]` plus a quality-regression gate. **ruff / eslint /
  mypy are NOT CI gates** — don't add local lint hooks expecting "CI parity"; the gate is pytest.
- **The full suite is ~17 min single-process on this WSL2 box** (LanceDB temp-table + RSS accumulation
  → swap; it's the long-lived process, not the work — a torch-free hermetic venv is equally slow). For
  a fast local loop, use a hermetic venv (no system site-packages) + a scoped run, e.g.
  `pytest tests/neuro_core tests/test_pipeline.py tests/test_retrieve.py tests/test_qa.py` (~20s). Let
  CI run the full suite as the comprehensive gate.
- **Never add `pytest-xdist -n auto`** — worker fan-out OOMs and crashes the WSL session.
- **Guard `streamlit` imports in tests.** Any test importing streamlit MUST start with
  `pytest.importorskip("streamlit")` before the import. `streamlit` is only in the `web` extra; required
  CI installs `.[dev]` (no streamlit), so a bare module-level import raises `ModuleNotFoundError`
  **at collection** and aborts the **entire** run (exit 2), not just that file. `pillow` is core (no
  guard needed). The `ci/hook_collect_check.py` precheck (advisory PostToolUse hook) catches this class
  of failure in seconds via `pytest --collect-only`.

## Web console (`web/`)

- **Two-token contrast model** (Tailwind v4 `@theme` in `web/src/index.css`): bright brand fills
  (`--color-primary #ff3333`, `--color-success`, `--color-amber`) carry **black** text; colored TEXT on
  white uses the darker `-ink` tokens (`--color-primary-ink #c8102e`, etc., all ≥5:1 on white). **Never**
  use `text-primary` / `text-success` / `text-amber` on a light surface — use `text-*-ink`. The bright
  tokens are for `bg-*` / `border-*` fills only.
- **Phone access:** `scripts/serve-phone.sh` serves the SPA+API on `0.0.0.0:8001` and prints a
  reachability banner. WSL2 needs mirrored networking or `scripts/wsl-portproxy.ps1` (elevated).
  Full runbook: `docs/SERVE_ON_PHONE.md`.
