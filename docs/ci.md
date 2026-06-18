# Continuous Integration

This repo's CI is built around one principle: **the per-PR gate exercises only the offline
default path** — no API keys, no GPU, no textbook corpus, no private index, no external
service at test time. The only network use is at *install* time (PyPI wheels). Heavier,
environment-dependent checks are split into a separate, non-blocking workflow.

> Design rationale and tradeoffs: `docs/superpowers/specs/2026-06-14-ci-system-design.md`
> (written when caseprep was an external pinned dependency; it is now vendored in-tree).

## caseprep is vendored in-tree

`caseprep` lives in this repo at [`vendor/caseprep/`](../vendor/caseprep/), brought in with
`git subtree` (full history preserved). Its package (`vendor/caseprep/caseprep`) is mapped to
the top-level `caseprep` import name (via `package-dir`) and imported by the pipeline/CLI — no
external folder, no editable sibling install, no pinned commit. It sits under `vendor/` rather
than `./caseprep` so the directory name can't shadow the `caseprep` import when the repo root is
on `sys.path`. A clean clone plus `pip install -e .[dev]` gets everything, and caseprep's own
tests run as part of this repo's suite (`testpaths` includes `vendor/caseprep/tests`).

- The shared installer `ci/install.sh "<target>"` just installs the given pip target
  (e.g. `".[dev]"` or `dist/*.whl`); caseprep comes with it.
- To pull upstream caseprep changes later: `git subtree pull --prefix=vendor/caseprep <remote> <ref>`.

## Required workflow — `.github/workflows/ci.yml`

Runs on every PR and on pushes to `master`. These three jobs are the **branch-protection
candidates**.

| Job | What it proves | Why it is reliable |
|-----|----------------|--------------------|
| **`sanity`** | Every `.py` under `neuro_caseboard/`, `neuro_core/`, `app/`, `tests/`, `eval/` byte-compiles (catches syntax errors fast); `pyproject.toml` is valid TOML; no unresolved merge-conflict markers. | Pure syntax/text checks; no heavy install; first-failure signal in <30 s. |
| **`test`** (Python 3.10 + 3.12) | The real core behavior — `model`/`compile`/`render_md`/`render_pdf`/`dedup`/`captions`/`guard`/`pipeline`/`cli` plus `neuro_core` retrieval & figure logic — the offline on-disk **LanceDB integration** tests, and the **CLI artifact smoke** (`tests/test_cli_smoke.py`). Regression protection. | All ML backends are dependency-injected/faked and heavy libs import lazily, so the suite is offline/CPU/no-download. `PYTHONHASHSEED=0`. |
| **`package`** | `python -m build` produces a valid sdist+wheel; `twine check` passes; a **clean venv** install of just the wheel (declared deps resolve from PyPI; caseprep is bundled in the wheel) yields importable modules and a working `caseboard --help`. | This is the install/dependency/entry-point gate — it is what catches a future undeclared top-level import or broken metadata. |

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

## Keyed nightly workflow — `.github/workflows/live-judge.yml`

`workflow_dispatch` (manual) + a nightly schedule (07:23 UTC). **Not** a required gate and it
**never blocks a PR** — it is the keyed run of the live BLIND judges, the real quality signal that
the offline `eval/quality_gate.py` cannot measure (it needs a credentialed LLM + vision provider).

| Step | What it does |
|------|--------------|
| **gate** | If `CASEBOARD_LLM_PROVIDER` + `GOOGLE_CLOUD_PROJECT` secrets are absent, the job is a clean, green **no-op** (every later step is skipped). So forks and the nightly schedule never fail for lack of credentials. |
| **text judge** | `eval/live_text_judge.py` on the held-out **eval** split — an attending-examiner persona grades each dossier vs `cases.json` `must_cover` / `red_flags`. |
| **image judge** | `eval/live_image_judge.py --backend vertex --budget 3.0` on the eval split — a vision model opens each rendered PNG and grades conceptual correctness + case-specificity. Keeps its `--budget` hard-stop. |
| **artifacts** | The dated `CASE_TEXT_JUDGE_REPORT_*` / `CASE_IMAGE_JUDGE_REPORT_*` reports upload via `actions/upload-artifact@v5`. |

Secrets (repository → Settings → Secrets): `CASEBOARD_LLM_PROVIDER` (e.g. `vertex`),
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CREDENTIALS` (service-account JSON for ADC), and optionally
`OPENROUTER_API_KEY`. Run it by hand from the Actions tab (**Run workflow**) or let the nightly cron
fire. Metrics are tracked informationally against `eval/LIVE_BASELINE.json` (prior measured scores +
this loop's targets); backfill the measured numbers there after a keyed run.

To run the judges locally instead (same as the workflow, eval split):

```bash
IDS=$(python -c "import json;print(','.join(c['id'] for c in json.load(open('eval/cases.json'))['cases'] if c['split']=='eval'))")
CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_text_judge.py --ids "$IDS" --tag local
CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_image_judge.py --backend vertex --ids "$IDS" --budget 3.0 --tag local
```

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
| core | fpdf2, pillow, pymupdf, httpx, lancedb, numpy + caseprep's deps (mcp, fastapi, uvicorn, requests, pandas, pydantic, markdown) | `[project].dependencies` | yes |
| vendored | caseprep (in-tree at `vendor/caseprep/`) | `git subtree`, mapped via `package-dir` | yes (bundled) |
| dev | pytest, pytest-asyncio, pdfplumber | `[dev]` extra | yes |
| llm / vertex | anthropic / google-genai | `[llm]` / `[vertex]` extras | no (local/runtime) |
| briefing | playwright | `[briefing]` extra | optional workflow |
| web | streamlit | `[web]` extra | no (syntax-checked only) |
| models | sentence-transformers, open-clip-torch | `[models]` extra | optional workflow |
