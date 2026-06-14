# Continuous Integration

This repo's CI is built around one principle: **the per-PR gate exercises only the offline
default path** — no API keys, no GPU, no textbook corpus, no private index, no external
service at test time. The only network use is at *install* time (PyPI wheels + one pinned
git dependency). Heavier, environment-dependent checks are split into a separate,
non-blocking workflow.

> Design rationale and tradeoffs: `docs/superpowers/specs/2026-06-14-ci-system-design.md`.

## The one external dependency: caseprep

`caseprep` is a sibling library (public repo
`github.com/michaelandrewlongo-rgb/caseprep`) imported at module top by the pipeline/CLI.
It is **not** declared in `pyproject.toml` (so the local `pip install -e ../caseprep`
workflow is preserved), so every environment must install it first. CI installs it from a
**pinned commit** via the `CASEPREP_REF` workflow variable, so runs are reproducible.

- To bump it: change `CASEPREP_REF` in `.github/workflows/ci.yml` **and**
  `.github/workflows/optional-integration.yml` **and** the default in `ci/install.sh`.
- The shared installer `ci/install.sh "<target>"` installs the pinned caseprep, then the
  given pip target (e.g. `".[dev]"` or `dist/*.whl`).

## Required workflow — `.github/workflows/ci.yml`

Runs on every PR and on pushes to `master`. These three jobs are the **branch-protection
candidates**.

| Job | What it proves | Why it is reliable |
|-----|----------------|--------------------|
| **`sanity`** | Every `.py` under `neuro_caseboard/`, `neuro_core/`, `app/`, `tests/`, `eval/` byte-compiles (catches syntax errors fast); `pyproject.toml` is valid TOML; no unresolved merge-conflict markers. | Pure syntax/text checks; no heavy install; first-failure signal in <30 s. |
| **`test`** (Python 3.10 + 3.12) | The real core behavior — `model`/`compile`/`render_md`/`render_pdf`/`dedup`/`captions`/`guard`/`pipeline`/`cli` plus `neuro_core` retrieval & figure logic — the offline on-disk **LanceDB integration** tests, and the **CLI artifact smoke** (`tests/test_cli_smoke.py`). Regression protection. | All ML backends are dependency-injected/faked and heavy libs import lazily, so the suite is offline/CPU/no-download. `PYTHONHASHSEED=0`. |
| **`package`** | `python -m build` produces a valid sdist+wheel; `twine check` passes; a **clean venv** install of just the wheel (declared deps resolve from PyPI) + pinned caseprep yields importable modules and a working `caseboard --help`. | This is the install/dependency/entry-point gate — it is what catches a future undeclared top-level import or broken metadata. |

### The CLI artifact smoke (what it specifically guards)

`tests/test_cli_smoke.py` (marker `smoke`) shells out to the real `caseboard` entry point:

```
caseboard build "C5-6 corpectomy" --no-llm --pdf -o <tmp>
```

with `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GOOGLE_CLOUD_PROJECT`,
`CASEBOARD_LLM_PROVIDER`, `CASEBOARD_LLM`, and `CASEPREP_TEXTBOOK` **stripped from the
environment**. It asserts a non-trivial Markdown (topic title, marker legend, sections) and
a real `%PDF` are produced. That proves the rendering/export surface generates artifacts on
the deterministic offline path with **zero hidden dependence** on keys, a corpus, or a GPU.

## Optional / manual workflow — `.github/workflows/optional-integration.yml`

`workflow_dispatch` (manual) + a weekly schedule. **Not** a required gate. It exercises the
heavy optional surfaces that *can* run on a hosted runner:

| Job | What it proves | Constraint |
|-----|----------------|------------|
| **`briefing-pdf`** | The `briefing` extra installs and Playwright/Chromium renders the Signal-styled PDF from a Q&A-shaped result. | Installs Chromium; minutes; uploads the PDF as an artifact. |
| **`models-smoke`** | The `models` extra installs and the lazy embedding seam works against a **real** backend (a small model actually embeds). | Downloads a model from Hugging Face; network; minutes. |

### Documented local-only (cannot run in hosted CI)

These need GPUs, billed API keys, or the private textbook corpus, so they are intentionally
**not** automated. Run them locally when relevant:

- `caseboard ask "<question>"` — GPU readiness guard + real retrieval + synthesis.
- Real LanceDB corpus build and the BiomedCLIP visual figure lane (needs the textbook PDFs
  and `TEXTBOOK_INDEX_DIR`/`ASSETS_DIR`).
- The Vertex/Anthropic LLM Explorer (`caseboard build` without `--no-llm`) — needs
  `GOOGLE_CLOUD_PROJECT` + ADC, or `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`.
- `eval/` corpus scorers — need the private textbook corpus.

## Reproduce CI locally

```bash
ci/local-ci.sh                       # full mirror: sanity -> tests -> package smoke
USE_LOCAL_CASEPREP=1 ci/local-ci.sh  # faster: install caseprep from ../caseprep instead of git
```

The mirror builds a throwaway venv **without** system site-packages, so globally-installed
heavy libraries (torch, sentence-transformers, open-clip) cannot leak in and mask a missing
declaration — the same isolation the GitHub runners give you.

### Faster local test loops

```bash
pytest                       # everything (what CI runs)
pytest -m "not integration"  # skip the on-disk LanceDB tests
pytest -m "not smoke"        # skip the subprocess CLI/PDF smoke
pytest -m smoke              # only the CLI artifact smoke
```

## Recommended branch protection

Require these status checks on `master`:

- `sanity (syntax + repo hygiene)`
- `test (py3.10)`
- `test (py3.12)`
- `package (build + clean install + entry point)`

Leave `optional-integration` **unchecked** (manual/scheduled).

## Dependency tiers

| Tier | Packages | Declared where | In required CI? |
|------|----------|----------------|-----------------|
| core | fpdf2, pillow, pymupdf, lancedb, numpy | `[project].dependencies` | yes |
| external | caseprep | pinned git (`CASEPREP_REF`) | yes (installed first) |
| dev | pytest, pdfplumber | `[dev]` extra | yes |
| llm / vertex | anthropic / google-genai | `[llm]` / `[vertex]` extras | no (local/runtime) |
| briefing | playwright | `[briefing]` extra | optional workflow |
| web | streamlit | `[web]` extra | no (syntax-checked only) |
| models | sentence-transformers, open-clip-torch | `[models]` extra | optional workflow |
