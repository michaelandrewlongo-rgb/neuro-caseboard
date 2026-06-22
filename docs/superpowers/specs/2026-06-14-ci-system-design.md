# CI System — Design & Tradeoffs

Date: 2026-06-14
Status: implemented

## Goal

Give high confidence that a PR can safely merge into `master`, by catching the failure
modes this project is actually exposed to: **offline build, packaging, import,
dependency, and entry-point breakage; CLI behavior; and artifact (PDF/Markdown)
generation** — without depending on local corpora, API keys, GPUs, private indexes, or
external services.

## Risk profile (what we learned from the code)

The repo is two in-tree packages (`neuro_caseboard`, `neuro_core`) plus a Streamlit
`app/`, an `eval/` harness, and a `tests/` suite (295 tests). Key facts that shape the
design:

1. **The offline core is test-friendly.** Every heavy ML component is
   dependency-injected (`Embedder(encoder=...)`, `Reranker(scorer=...)`,
   `VisualEmbedder(backend=...)`, synth clients) and the heavy libraries
   (`torch`, `sentence_transformers`, `open_clip`) are imported **lazily inside
   methods**. The whole suite therefore runs offline, CPU-only, with no model
   downloads, in ~6 s. Proven empirically in a clean venv: **294/295 pass with
   torch / sentence-transformers / open-clip / GPU entirely absent.**

2. **The install boundary is the real risk.** The advertised entry point
   `caseboard` (`neuro_caseboard.cli:main`) imports, at module top:
   - `caseprep.*` (via `pipeline.py`, `guard.py`, `explore_llm.py`, `render_pdf.py`)
   - `neuro_core.index` → `import lancedb` (via `retrieve.py`)

   `caseprep` is a **public sibling git repo**
   (`github.com/michaelandrewlongo-rgb/caseprep`, HTTP 200, light deps — no torch /
   lancedb). `lancedb` is a normal PyPI wheel (CPU). **Neither was declared** in
   `pyproject.toml`, so `pip install . && caseboard --help` failed before this work.

3. **One non-deterministic test.** `tests/test_explore_llm.py::test_llm_available_with_vertex`
   asserts `llm_available() is True` for the Vertex provider, which is only true if
   `google.genai` is importable. `google-genai` is declared in **no** extra, so the test
   passed only on machines that happened to have it installed. This is precisely the
   hidden-dependency trap CI must remove.

4. **`caseboard build --no-llm --pdf` is the offline artifact path.** It uses caseprep's
   deterministic rule-based Explorer → Enricher (no retriever) → compile → **fpdf2**
   render. It produces a valid `%PDF-1.3` + Markdown with no key/corpus/GPU. (`caseboard
   ask` is *not* offline — it needs a real index, GPU guard, and synthesis — so it is not
   a CI smoke target.)

5. **Streamlit app** runs `st.set_page_config()` at import, so it is only suitable for a
   *syntax* (compileall) check in required CI, not a runtime import smoke.

## Dependency model used by CI

| Tier | Packages | Where | CI treatment |
|------|----------|-------|--------------|
| core (declared) | fpdf2, pillow, pymupdf, **lancedb**, **numpy** | `[project].dependencies` | installed everywhere (required) |
| external sibling | **caseprep** | public git, pinned SHA | installed before the package in every required job |
| dev | pytest, pdfplumber | `[project.optional-dependencies].dev` | required |
| vertex / briefing / web / models | google-genai / playwright / streamlit / sentence-transformers+open-clip-torch | extras | optional workflow / local only |

`lancedb`+`numpy` were promoted into core deps because the entry point cannot import
without them — this is a correctness fix, not a footprint expansion of *runtime behavior*.
`caseprep` is deliberately kept out of `pyproject` core deps (it is git-only and the
project's convention is an editable `-e ../caseprep` install for local dev); CI installs
it explicitly from a **pinned commit** so runs are reproducible.

## Required workflow — `ci.yml` (branch-protection candidates)

Triggers: `pull_request` and `push` to `master`. Concurrency-cancel per ref.
Global determinism: `PYTHONHASHSEED=0`, `PIP_DISABLE_PIP_VERSION_CHECK=1`, pinned action
versions, pip cache keyed on `pyproject.toml`, pinned `CASEPREP_REF`.

| Job | What it proves | Why it can't flake |
|-----|----------------|--------------------|
| `sanity` | Every `.py` in the repo byte-compiles; no merge markers; `pyproject` parses. Fast feedback (<30 s, no heavy install). | Pure syntax/text checks. |
| `test` (3.10, 3.12) | The real core behavior — render/compile/dedup/captions/guard/pipeline/cli + neuro_core retrieval/figure logic — and regressions, plus the offline `integration` LanceDB-on-disk tests and the CLI artifact smoke. | All ML injected/faked; no network in tests; deterministic hash seed. |
| `package` | `python -m build` produces a valid sdist+wheel; `twine check` passes; the **wheel** installs into a clean venv (declared deps resolve from PyPI) alongside caseprep; every public module imports; `caseboard --help` works. | Catches undeclared deps, broken metadata, missing entry point. |

The CLI smoke is a pytest test (`tests/test_cli_smoke.py`, marker `smoke`) that runs
`caseboard build --no-llm --pdf` in a **scrubbed environment** (no `OPENROUTER_API_KEY`,
`GOOGLE_CLOUD_PROJECT`, `CASEPREP_TEXTBOOK`) and asserts the
Markdown + a real PDF are produced — proving the offline path has no hidden dependence on
keys/corpora.

## Optional / manual workflow — `optional-integration.yml`

Triggers: `workflow_dispatch` + weekly schedule. Non-blocking (not branch-protection).

| Job | What it proves | Constraint |
|-----|----------------|------------|
| `briefing-pdf` | The `briefing` extra installs and Playwright/Chromium renders the Signal-styled PDF from a fixture Q&A result. | Heavy (chromium); fonts via CDN best-effort. |
| `models-smoke` | `sentence-transformers` installs (CPU) and a tiny model actually embeds — i.e. the lazy ML seam works against a real backend. | Downloads a model from HF (network, minutes). |

Explicitly **out of automated CI** (documented as local-only): the GPU-guarded
`caseboard ask` path, real LanceDB corpus build/visual BiomedCLIP lane, the
Vertex/Anthropic LLM Explorer, and the `eval/` corpus scorers — all require GPUs, billed
API keys, or private textbook corpora that hosted runners do not have.

## Tradeoffs

- **Promoting lancedb/numpy to core deps vs. an extra.** Chose core deps: the entry point
  *requires* them, so an extra would ship a broken `caseboard`. Cost: a heavier base
  install for a hypothetical render-only consumer. Reversible in one edit.
- **Pinned-git caseprep vs. vendoring vs. PyPI direct-URL in pyproject.** Chose
  install-time pinned git in the workflow: reproducible, preserves the local editable
  workflow, keeps `pyproject` index-installable. Cost: a caseprep change needs a
  `CASEPREP_REF` bump (a feature — explicit, reviewable).
- **Running `integration` tests in required vs. optional.** They are offline + fast +
  deterministic (real LanceDB on a temp dir), so they run in required for stronger
  coverage; the marker still allows `-m "not integration"` for an even faster local loop.
- **Make the flaky vertex test hermetic vs. add a `vertex` dep to CI.** Chose hermetic
  (inject a fake `google.genai` into `sys.modules`) — keeps required CI free of an
  external-service SDK and matches the test file's stated "never touch the network" intent.
- **Two Python versions, not four.** 3.10 (declared floor) + 3.12 (modern) balances
  coverage against PR latency.

## Local reproduction

`ci/local-ci.sh` builds a throwaway venv and runs the exact required sequence (caseprep
pin → install → sanity → tests → package smoke), so a red CI job can be reproduced and
debugged locally with one command.
