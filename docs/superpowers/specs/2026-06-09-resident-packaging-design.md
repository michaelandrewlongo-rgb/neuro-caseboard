# Resident-ready packaging + MCP server — design

**Date:** 2026-06-09
**Status:** approved (brainstorming)

## Goal

Any medical resident with no AI or programming background can download this tool,
point it at their own folder of textbook PDFs, run a few copy-paste commands, and
have a working personal, citation-grounded textbook Q&A system — on an ordinary
laptop with no GPU. Ship the new MCP server as part of the same package.

Success = a non-technical user on a plain MacBook or Windows laptop goes from
"never heard of this" to asking a question in the browser viewer using only the
README, with no human help; and an MCP-capable agent (Claude Code/Desktop) can
query the corpus through `textbook-rag mcp`.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Target hardware | Any laptop, **no GPU assumed** (CUDA/Apple-Silicon auto-detected as accelerators) |
| Synthesis for residents | **OpenRouter key only** in the wizard; Vertex/local stay env-only advanced options |
| Install path | **One-line installer + setup wizard** (terminal OK, every step copy-paste) |
| v1 scope | Core Q&A + **text-driven figures** (Phase 2a) + **MCP server** + **PubMed currency lane**; NO CLIP visual lane |
| Distribution | **New clean public repo**, no history; private repo stays the dev home |
| CPU query speed | **Hardware profiles**: small models on CPU, current large models on CUDA/MPS |

## 1. Public repo + release flow

- New public GitHub repo (working name `textbook-rag`; CLI command `textbook-rag`),
  created fresh with no history.
- Contents are exported from the private repo by an **allowlist export script**
  (`scripts/export_public.py` in the private repo): `engine/`, `server/`, `web/`,
  `cli/`, `scripts/` (curated subset), `tests/`, `pyproject.toml`, resident-facing
  `README.md`, `docs/how-it-works.md`, `LICENSE`, `.env.example`, installer scripts,
  CI workflows. **Never exported:** `docs/superpowers/` specs/plans, run logs,
  `VERIFICATION.md`-style artifacts, `eval/` answer files, `archive/`, `app/`
  (Streamlit), `Dockerfile`/cloud files, anything naming personal paths, GCP project
  IDs, or the personal corpus.
- Publishing = run the export script into a clean checkout of the public repo,
  review the diff, commit, tag a release. The private repo remains where development
  happens.
- **Prerequisites before first export:** PR #3 (PubMed reconciliation) and the
  currently-uncommitted live-reconcile lane (`engine/live_reconcile.py` + test)
  land on `master`. Marker (PR #1) and the local-quantized-synthesis branch are NOT
  prerequisites and are not part of the resident package.
- Packaging: the repo gains a `pyproject.toml` (PEP 621) so the project is
  `uv tool install`-able straight from the public GitHub repo. PyPI publication is
  optional later; the installer pins to the repo/tag, so PyPI is not a v1 requirement.

## 2. Resident UX — the four commands

**Install (one copy-paste line):**
- macOS/Linux: `curl -fsSL https://raw.githubusercontent.com/michaelandrewlongo-rgb/<public-repo>/main/install.sh | bash`
  (`<public-repo>` = the new public repo's final name, settled at creation since
  `textbook-rag` is currently taken by the private repo)
- Windows: equivalent one-line PowerShell (`irm … | iex`)
- The installer: installs `uv` if missing → `uv tool install` the package (pinned
  tag) → verifies `textbook-rag --version` runs → prints exactly one next step:
  "run `textbook-rag setup`". Python itself is provisioned by uv (no system-Python
  assumption — the known Windows failure point).

**`textbook-rag setup` — interactive wizard:**
1. Detects hardware (CUDA → MPS → CPU) and writes the profile (overridable).
2. Asks for the PDF folder; probes every PDF for a real text layer (reuse the
   existing probe); lists per-book page/figure counts; warns clearly on scanned
   books ("this book has no text layer and will be skipped — OCR is not supported").
3. Walks through OpenRouter signup in plain language (URL, add ~$5 credit, create
   key), then validates the pasted key with a live ping before accepting it.
4. Writes config to `~/.textbook-rag/config.env` (same key=value format as `.env`;
   the engine's config loader gains this fallback location). Index and figure
   assets live under `~/.textbook-rag/` too, not inside the install.
5. Offers to start indexing now.
6. Non-interactive mode (`--corpus-dir … --openrouter-key … --profile …`) exists
   for tests and power users.

**`textbook-rag index`:** per-book progress output, and **per-book resume**: books
already present in the index (keyed by file hash) are skipped, so a crash at book 9
restarts at book 9, not book 1. This fixes the known "index build is not
crash-resumable" limitation with a book-granularity upsert (append new / skip
unchanged / delete+re-append changed), independent of the Marker manifest work.

**`textbook-rag serve`:** starts the FastAPI server on localhost and opens the
browser viewer. `textbook-rag ask "…"` remains for the terminal.

## 3. Hardware profiles

| Profile | Embedder | Reranker | Selected when |
|---|---|---|---|
| `gpu` (CUDA or Apple MPS) | BGE-large-en-v1.5 (current) | bge-reranker-v2-m3 (current) | accelerator detected |
| `cpu` | bge-small-en-v1.5 | MiniLM-class cross-encoder (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`) | no accelerator |

- Implemented through the **existing config keys** (model names + `EMBED_DEVICE`);
  the profile is just a preset written by the wizard.
- Target: a few seconds per query on CPU (vs minutes with the 568M reranker —
  measured on the Cloud Run attempt). Indexing on CPU is slow-but-one-time and the
  wizard says so up front.
- The index records which embedder built it; querying with a mismatched profile
  fails with a clear "re-run `textbook-rag index`" message instead of silent
  garbage retrieval.

## 4. Synthesis

- Wizard path is **OpenRouter only**: one key, one code path
  (`OpenRouterSynthClient`, already exists and already supports attached figure
  images). Default model pinned to a cheap **multimodal** Gemini-Flash-class model
  (~half a cent per question at the current ~5K-in/~400-out call shape) so
  text-driven figure attachment keeps working.
- `SYNTH_PROVIDER=vertex|local` remain fully functional but env-only ("advanced"
  section of the README); the wizard never mentions them.

## 5. MCP server

- `textbook-rag mcp` runs a **stdio** MCP server (official `mcp` Python SDK) over
  the unchanged engine seam, exposing two tools:
  - `search_textbooks(question, k=…)` — retrieval only: passages with
    book/chapter/page plus matched figure paths. No synthesis call, so $0 per use;
    the calling model writes the answer.
  - `ask_textbooks(question)` — the full pipeline: synthesized, cited answer with
    the engine's refusal and disagreement behavior.
- Setup prints (and `textbook-rag mcp print-config` reprints) the exact
  `claude mcp add …` one-liner / JSON snippet for Claude Code and Claude Desktop.
- Engine models load lazily on first tool call (same warm-cache behavior as the
  server), so registering the MCP server costs nothing until used.

## 6. PubMed currency lane

- Ships exactly as merged from PR #3 + the live-reconcile lane: an appended
  "current literature" finding on clinician answers, never blocking or altering
  the grounded textbook answer (its existing failure-isolation contract:
  any failure → `literature=None`).
- Keyless NCBI E-utilities by default (3 req/s is plenty for single-user);
  `NCBI_API_KEY`/`NCBI_EMAIL` stay as optional config.

## 7. Figures (text-driven only)

- Phase 2a lane ships: figure pages detected and rendered at index time, attached
  via text retrieval, displayed in the viewer and cited.
- The CLIP visual lane does **not** ship: `open_clip_torch` moves to an optional
  dependency extra (`pip install "textbook-rag[visual]"`), keeping the resident
  install lighter and avoiding a second model download. The lane already degrades
  gracefully when the `figures` table is absent.

## 8. Error handling (wizard-grade)

- Every wizard step validates before moving on: folder exists and contains PDFs;
  text-layer probe per book; key validated by a live API ping; disk-space check
  before indexing (index + rendered figures can be several GB).
- Indexing failures name the book and page and continue with the next book where
  safe; the run summary lists skipped/failed books.
- Query-time failures distinguish: no index yet ("run `textbook-rag index`"),
  profile/index mismatch, missing/invalid key, OpenRouter balance exhausted
  (surfaces the provider's error in plain language).
- No service worker, no offline caching (standing project rule).

## 9. Testing / CI

- The existing test suite (115+ on the PubMed branch) is exported with the code.
- New tests: wizard logic via the non-interactive flags (no TTY emulation),
  profile selection/mismatch detection, per-book resume (index a 2-PDF fixture,
  delete one row-set, re-run, assert only the missing book re-embeds), MCP tools
  called in-process (both tools, plus refusal pass-through).
- GitHub Actions on the **public** repo: macOS / Windows / Linux matrix running
  the full CPU-profile path against a small fixture PDF — install, index, retrieve
  (no network synthesis; the synth client is stubbed). This is the standing proof
  that the resident path works on all three platforms.

## Out of scope (v1)

- CLIP/BiomedCLIP visual lane (optional extra, off by default)
- Marker extraction (PR #1) and any OCR for scanned books
- Desktop app (.exe/.dmg), phone/PWA, tunnels, Cloud Run
- PyPI publication (installer pins to the GitHub repo/tag)
- Vertex or local-Ollama synthesis in the wizard
- Auto-update mechanism (re-running the installer upgrades)
