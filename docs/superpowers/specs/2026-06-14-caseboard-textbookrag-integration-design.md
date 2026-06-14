# Integrating neuro-caseboard + textbook-rag into one product

**Date:** 2026-06-14
**Status:** Approved design (Phase 0 is the implementation target of this spec)
**Author:** Michael Longo + Claude

## 1. Context & problem

Two repositories currently form an implicit producer/consumer pair:

- **textbook-rag** (`/home/michael/neuro-textbook-rag`) — the retrieval engine: a LanceDB
  corpus index (chunks + figures), embed/rerank/synthesis pipeline, the figure lanes
  (page-text, BiomedCLIP visual, and the new Gemini-caption lexical lane), and three Q&A
  surfaces (CLI `cli.ask`, FastAPI `server`, Streamlit `app`). **Not pip-packaged** (top-level
  `engine/`, `cli/`, `server/`, `app/`, `scripts/`).
- **neuro-caseboard** (`/home/michael/projects/neuro-caseboard`) — the application: generates
  structured pre-operative case boards via a PLANNER→AUTHOR→CRITIC pipeline built on the
  external **`caseprep`** library. Packaged (`pyproject.toml`, package `neuro_caseboard`).

They are glued, not integrated:

- **Fragile seam.** `neuro_caseboard/retrieve.py` reaches into textbook-rag at runtime with
  `sys.path.insert(0, repo)` + `from engine.index import Index` (env-gated by
  `TEXTBOOK_RAG_REPO`/`TEXTBOOK_INDEX_DIR`, wrapped in broad `except: pass`). Because
  textbook-rag is not installable, this path hack is the only way in.
- **Duplicated figure logic.** As of 2026-06-14 there are **two** caption-lexical figure
  retrievers: textbook-rag's `engine/caption_index.py::CaptionIndex` (no guards) and
  caseboard's `neuro_caseboard/retrieve.py::FigureCaptionRetriever` (region/level/domain/
  anterior-posterior/flowchart/diagnostic guards + optional BiomedCLIP). The IDF ranking,
  caption handling, and `gemini_caption` preference are implemented twice.
- **Config split.** textbook-rag's `engine/config.py` vs caseboard's ad-hoc env vars.

The goal is a single product with both capabilities — Q&A and case boards — sharing one
retrieval/figure/citation core, so an improvement in one place benefits both, not two tools
bolted side by side.

## 2. Vision: one engine, two surfaces

```
                       ┌─────────────────────────────┐
                       │   neuro_core  (the engine)   │
                       │  corpus index · retrieval    │
                       │  figures: ONE lane (caption  │
                       │   + visual + guards-optional)│
                       │  citations · synth clients   │
                       └──────────────┬───────────────┘
              ┌───────────────────────┼───────────────────────┐
              ▼                                                 ▼
      ask() → cited answer + figures           generate_board() → structured pre-op board
              └───────────────────────┬───────────────────────┘
                          one CLI · one web app · one deploy
            cross-feature: board card → "ask a follow-up"; answer → "build a board"
```

Corpus, retrieval, the figure/caption/guard logic, and citations are computed **once** in a
shared core; Q&A and boards become two thin features over it.

## 3. Decision

- **Approach A — monorepo with a shared importable `neuro_core`**, rooted in the existing
  **neuro-caseboard** repo (higher-level product; the only one already packaged).
- **`caseprep` stays an external dependency** (a separate library; not in scope to merge).
- Chosen over: (B) package textbook-rag and `pip install` it into caseboard with two repos kept
  — least work but stays "two products in a trench coat," weak on cross-feature flows; (C)
  absorb the engine under `neuro_caseboard/core` — one repo fast, but re-homes textbook-rag's
  Q&A surfaces awkwardly and muddies naming.

## 4. Phased decomposition

Each phase is independently shippable and gets its own plan. **This spec implements Phase 0.**

- **Phase 0 — shared core + de-dup + glue removal.** Extract `neuro_core`, collapse the two
  figure retrievers into one, repoint all imports, delete the `sys.path` hack. Behavior
  unchanged; verified by the existing test suites. *(This document.)*
- **Phase 1 — unified surface.** One CLI + one web app exposing both Q&A and board generation
  over the shared core (shared figures/citations/captions). *(Future spec.)*
- **Phase 2 — cross-feature flows.** Board card ↔ Q&A follow-up; answer → "build a board"; a
  shared evidence model. *(Future spec.)*

## 5. Phase 0 detailed design

### 5.1 Scope boundary
Phase 0 **moves and unifies trusted code behind unchanged behavior**. It does **not** change the
two user surfaces — textbook-rag's `cli.ask`/server/app and caseboard's board generator keep
working exactly as today, now importing the shared core. No new user-facing behavior.

### 5.2 Target layout
```
neuro-caseboard/                 (the one repo)
  pyproject.toml                 one project; packages = neuro_core, neuro_caseboard, qa
  neuro_core/                    (was textbook-rag/engine, now importable)
    config.py  index.py  embed.py  rerank.py  synth_clients.py  gpu_guard.py
    visual_embed.py  visual_index.py  ingest.py  synthesize.py  query.py
    figures.py                   figure extraction/crop (build-time)
    figure_retriever.py          UNIFIED retrieval lane (see 5.3)
    figure_guards.py             guards moved out of caseboard/retrieve.py
    scripts/                     build_index, build_visual_index, recaption_figures,
                                 caption_review_html
  neuro_caseboard/               board generation (explore_llm, pipeline, guard, captions,
                                 render_pdf); retrieve.py now imports neuro_core
  qa/                            Q&A surface (was textbook-rag cli/ + server/ + app/)
  tests/                         merged suites (neuro_core + neuro_caseboard)
  index/ , assets/               gitignored data, referenced via neuro_core.config
```

### 5.3 Unified figure lane (the crux)
Replace `CaptionIndex` (textbook-rag) and `FigureCaptionRetriever` (caseboard) with one module:

`neuro_core/figure_retriever.py`
- **Loader:** read the `figures` table once → rows with `book, page, figure_path, caption,
  gemini_caption, vector, context` (context joined from `chunks` as today).
- **Ranking:** IDF caption-lexical over the effective caption (`gemini_caption` if present, else
  source), with the medical synonym expansion; optional BiomedCLIP semantic lane behind a flag;
  RRF fusion when both lanes are active (current caseboard behavior).
- **Guards (optional, topic-aware):** delegate to `figure_guards.py`. **Default off** (free-text
  Q&A passes no topic); **boards pass a `topic`** and the guards run (cranial↔spine,
  anterior↔posterior-fossa, sellar, level/CVJ-subaxial, peripheral-nerve, diagnostic-image,
  non-operative-angio, flowchart-demote, vignette-demote).
- **Return type:** a neutral `FigureHit` dataclass. Thin adapters:
  - `to_hit(figure_hit) -> neuro_core.index.Hit` — for `query._collect_figures` fusion (Q&A).
  - `to_evidence(figure_hit) -> caseprep EvidenceRecord` — for the board pipeline.
- **Public API (stable interface):**
  - `FigureRetriever(rows, *, embed_fn=None)` and module helper
    `build_figure_retriever(index_dir=None, *, semantic=False)`.
  - `FigureRetriever.retrieve(query, *, topic="", top_n=8) -> list[FigureHit]`
    (callers pass their own `top_n`; `topic=""` ⇒ guards skipped; topic set ⇒ guards applied).
  - `caption_by_path: dict[str,str]` for display-time caption override (Q&A engine uses it).

Consumers after this change:
- `neuro_core/query.py::_collect_figures` builds the retriever once, calls `retrieve(question,
  topic="")` (guards off), fuses by `figure_path` with the text + visual lanes (unchanged),
  displays the gemini caption.
- `neuro_caseboard/retrieve.py` builds the retriever, calls `retrieve(fig_query, topic=topic)`
  (guards on) per anatomy card and adapts to `EvidenceRecord`.

### 5.4 Config unification
One `neuro_core.config` (textbook-rag's `Config`, already carrying corpus/index/model/figure
flags incl. `caption_retrieval`). Caseboard's `CASEPREP_TEXTBOOK`/`TEXTBOOK_RAG_REPO`/
`TEXTBOOK_INDEX_DIR` are removed; the figure lane and textbook lane read `neuro_core.config`
directly. The board pipeline keeps its own board-specific env (`CASEBOARD_*`, LLM provider) —
those are board concerns, not core concerns.

### 5.5 Glue removal
Delete from `neuro_caseboard/retrieve.py`: `_default_textbook_repo`, the `sys.path.insert`,
the `from engine.* import` blocks and their `except: pass`, and the legacy `engine.query.search`
fallback. The in-process textbook lexical lane (`_index_search_fn`) becomes a direct
`from neuro_core.index import Index`.

### 5.6 Migration & git history
Bring textbook-rag's tree into the monorepo via **`git subtree add`** (preserves its commit
history under `neuro_core/` + `qa/`), then a single mechanical pass repoints `engine.* →
neuro_core.*` across the moved cli/server/app/eval and across caseboard. `index/` and `assets/`
are **not** committed (gitignored, large); they stay on disk and are found via config.

## 6. Acceptance criteria
- Merged suite green: the current **178 (caseboard) + 112 (textbook-rag)** tests pass together.
- `figure_eval` MCA/CPA/C1-C2 figures identical to the shipped after-guards result.
- A real `ask()` and a real board produce the same figures + citations as before Phase 0.
- Static checks: **no** `sys.path.insert` or `from engine import` remains in caseboard; exactly
  **one** figure-retriever class in the tree; `import neuro_core` works without env vars.

## 7. Testing strategy
- Move each module's tests with it; they must pass unchanged (behavior is preserved).
- Add focused tests for `figure_retriever`: guards-off vs guards-on parity with the two old
  retrievers on representative inputs (MCA bullseye surfaces; CPA anterior-circulation plate
  blocked only when topic set; flowchart demoted).
- Keep the GPU-dependent visual tests as-is; do not run GPU pytest during the migration build.

## 8. Risks & mitigations
- **Import churn breaks something silently** → the broad `except: pass` in the old glue hid
  failures; the migration removes it, so a missing import now raises. Mitigate with the merged
  suite + a real `ask()`/board smoke run in acceptance.
- **Two `config` objects diverge mid-migration** → unify config first, before moving consumers.
- **Subtree history noise** → acceptable; preserves authorship. A clean copy is the fallback if
  subtree proves messy.
- **Hidden caseprep coupling** → caseprep stays external and untouched; only caseboard's
  *retrieval* wiring changes.

## 9. Out of scope (Phase 0)
- Unifying the user surfaces (one CLI/app) — Phase 1.
- Cross-feature flows (board↔Q&A) — Phase 2.
- Merging or modifying `caseprep`.
- Moving/rebuilding the `index/` or `assets/` data.
- Renaming the product/repo (can happen later; Phase 0 keeps the caseboard repo name).

## 10. Resolved decisions
- Repo home: **neuro-caseboard** (monorepo root).
- History: **git subtree** (clean copy as fallback).
- Q&A surface package name: **`qa/`** (Phase 0 keeps textbook-rag's cli/server/app behavior;
  Phase 1 may rename).
