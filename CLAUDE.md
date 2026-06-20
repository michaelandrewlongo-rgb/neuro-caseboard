# CLAUDE.md — Neuro·Caseboard

Project-specific gotchas that are **not derivable from the code**. Generic workflow discipline
(TDD-first, verify-before-claiming-done) is already enforced by the superpowers skills, so this file
captures only what those skills can't know about this repo and this machine.

## Environment & runtime (this machine)

- **LLM provider is Vertex, not Anthropic.** Synthesis uses `SYNTH_PROVIDER=vertex`,
  `VERTEX_MODEL=gemini-2.5-pro` (needs `GOOGLE_CLOUD_PROJECT`, ADC at
  `~/.config/gcloud/application_default_credentials.json`, and `google-genai`). No `ANTHROPIC_API_KEY`
  is needed. The defaults in `neuro_core/config.py` are stale — probe Vertex, not an Anthropic key, in
  any health check.
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
