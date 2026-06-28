# neuro-caseboard — Architecture & Data-Flow Report

> **Source coverage.** This report fuses verified mapper analyses of all five subsystems (P1–P5), each grounded in a direct read of the source, and reflects the **`master` branch** (synced to `a8b90d9` at the time of writing). A few claims that require live credentials or a running renderer (LLM-judge scores, actual PDF/figure rendering fidelity, live LanceDB row counts) were read from their generators/call-sites but not executed; these are flagged inline. See `NEURO_CASEBOARD_DIAGRAMS.md` for the companion figures.

---

## 1. What neuro-caseboard is

neuro-caseboard is a citation-grounded case-preparation tool for a neurosurgeon. Its core job is to turn a free-text prompt — a procedure topic, a clinical dictation, or a single question — into a board-style briefing whose every claim is traceable to a real source, either a passage from an indexed neurosurgical textbook corpus or a contemporary PubMed study. The guiding invariant across the whole system is that **citations are only ever withheld, never fabricated**: if the engine cannot ground a statement, it drops the citation (or abstains entirely) rather than inventing one.

Under the hood it is a retrieval-augmented generation system with unusually heavy guardrails. A self-contained knowledge engine (`neuro_core/`) runs hybrid lexical+vector search over a LanceDB index of textbook chunks, plus a parallel lane that retrieves anatomical figure plates and a third isolated lane of board-review flashcards. An orchestration layer (`neuro_caseboard/`) wraps that engine, adds a live PubMed literature lane, runs the answer through entailment checks and deterministic content guards, and compiles the result into a structured `Dossier` or typed `OperativeBriefing`. Renderers turn those models into Markdown and PDF; surfaces (CLI, FastAPI, React SPA, Streamlit) expose the same engine to a human.

The product has three distinct "shapes" of output: **Build** (a topic → a structured case board), **Case** (a clinical dictation → an 8-section case dossier and operative briefing), and **Ask** (a question → a woven textbook + literature answer). All three flow through the same retrieval, verification, and rendering machinery.

---

## 2. System at a glance

| Subsystem | Owning paths | One-line job |
|---|---|---|
| **P1 — Knowledge & Retrieval Core** | `neuro_core/` | Citation-grounded hybrid search + figure/cards retrieval over a LanceDB index; exposes synthesize-and-answer and retrieval-only APIs. |
| **P2 — Orchestration Spine, Domain Models & Literature** | `neuro_caseboard/` (pipeline, qa, compile, model, briefing, intake, `literature/`, …) | Drives Build/Case/Ask paths, owns the `Dossier`/`OperativeBriefing` models, weaves in PubMed. |
| **P3 — Verification, Grading, Guards, Feedback & Eval** | `neuro_caseboard/{entailment,answer_verify,evidence_grade,guard,dedup,feedback,preferences}.py`, `eval/`, `evaluation/`, `gui-council/` | Decides what is trustworthy: entailment gate, claim verification, evidence grading, anti-bleed guards, surgeon feedback loop, regression harnesses. |
| **P4 — Output Generation & Rendering** | `neuro_caseboard/{render_md,render_pdf,briefing_pdf,operative_briefing_pdf,caseboard_pdf,fpdf_base,exec_navy,board_view,captions,briefing_figures}.py`, `figures_gen/`, `assets/` | Turns in-memory models into Markdown, PDF, Streamlit payloads, and generated schematic figures. |
| **P5 — Interfaces, Surfaces & Deployment** | `neuro_caseboard/cli.py`, `api/`, `app/`, `web/`, `scripts/`, `ci/`, `.github/`, `Dockerfile`, `tests/` | CLI / FastAPI / React / Streamlit surfaces over the one engine, plus build/deploy/test plumbing. |

---

## 3. Subsystem deep-dives

### P1 — Knowledge & Retrieval Core (`neuro_core/`)

P1 is a self-contained, literature-agnostic retrieval library. The rest of the product treats it as a black box. It runs **three parallel lanes over one LanceDB directory** (`INDEX_DIR`, live at `/home/michael/neuro-textbook-rag/index`):

- **Textbook chunk lane** (`chunks.lance`): `chunk.py` slides a ~600-word window over page text into `Chunk` records (carrying `book/chapter/page` + figure metadata); `embed.py` encodes them with BGE-large-en-v1.5; `index.py` stores vectors + a Tantivy FTS index and does hybrid search (vector kNN + full-text fused by `reciprocal_rank_fusion(k=60)` into `Hit` objects); `rerank.py` rescores with a `bge-reranker-v2-m3` cross-encoder.
- **Figure/visual lane** (`figures.lance`): `figures.py` crops per-plate PNGs with PyMuPDF; `visual_embed.py` embeds them with BiomedCLIP; `visual_index.py` owns the table; `figure_retriever.py` ranks figures by an IDF caption-lexical match (preferring Gemini-rewritten captions) optionally RRF-fused with the BiomedCLIP semantic lane; `figure_guards.py` blocks off-region/off-level/non-anatomical plates.
- **Board-review cards lane** (`cards.lance`): `cards_index.py`/`cards_query.py`/`cards_precision.py` mirror the chunk lane's machinery but store Q/A cards and — critically — return matched cards **verbatim with NO LLM synthesis**. Isolation is by table identity + a separate engine singleton.

The orchestration heart is **`query.py`**'s `Engine`: `_retrieve` (embed → hybrid_search(40) → rerank all → sink off-subdomain vascular hits → top 12), `_plan_query` (variant disambiguation via `query_analyze.py`), `_collect_figures` (fuse three figure lanes, apply strict region guard, re-root asset paths, assign citation source numbers), and `_answer` (synthesize). The key design decision is that the Engine exposes **both** a full path (`query()` → `QueryResult`) **and** a retrieval-only path (`plan_retrieval()` → `RetrievalBundle`) so P2 can weave PubMed evidence in itself.

Supporting infra: `config.py` (env → `.env` → stale `DEFAULTS`), `asset_paths.py` (re-roots build-time figure paths onto runtime mounts), `gpu_guard.py` (VRAM preflight, enforced only for the local LLM provider), `synth_clients.py` (OpenRouter `glm-5.2` is the default Ask-synthesis backend; Vertex Gemini and local Ollama are alternates, all behind a uniform `.generate`), and build/audit scripts under `neuro_core/scripts/` (`build_index`, `build_visual_index`, `build_cards_index`, `recaption_figures`, `purge_contamination`, `probe_book`, `audit_corpus_gaps`).

### P2 — Orchestration Spine, Domain Models & Literature (`neuro_caseboard/`)

P2 sits between the surfaces, the vendored **caseprep** Explorer/Enricher/Auditor, the P1 engine, and the P3/P4 helpers. Two orchestration paths:

- **Build path (`pipeline.py`).** `build_dossier(topic)` → `_resolve_manifest` decides LLM-first (`explore_llm.py`'s planner → author → critic, seeded by `ontology.py` required dimensions) vs. deterministic (`_deterministic_manifest`), stamping a **PHI-safe `Provenance` reason code once** at the decision point. The manifest passes through `guard.prune_offtarget` [P3] and optional `preferences.apply_preferences` [P3], then caseprep `enrich_manifest`/`audit_manifest`, then `compile.compile_dossier` assembles a `model.Dossier`. A parallel **Case path** builds an 8-section dossier from a `CaseContext` (`intake.py` dictation → `case_context.py` → `case_author.py` authors cards across `case_sections.py` surfaces), and `build_briefing_bundle` reuses that substrate to produce an `OperativeBriefingBundle`.
- **Ask path (`qa.py`).** `answer_question` runs **Lane A** (textbook retrieval+synthesis via P1) and **Lane B** (PubMed literature) concurrently in a `ThreadPoolExecutor`; in woven mode `_answer_question_woven` calls `neuro_core.plan_retrieval` + a literature retrieve concurrently and merges them in `woven_synth.synthesize_woven` into one answer with distinct `[n]` (textbook) and `[L#]` (PubMed) citation namespaces. **Lane B is strictly additive**: any failure → `literature=None`, never blocking Lane A — enforced at three layers (try/except→None, returns `[]` on failure, executor-future catch).

The **domain model** (`model.py`): `Dossier` → `Section` → `Claim` (with `grade`, `status`, `sub_items`) + `FigureItem` + `EvidenceSummary`; `briefing_model.py` is the Pydantic v2 `OperativeBriefingBundle` with `BRIEFING_SCHEMA_VERSION = 1` (serializes through FastAPI and drives generated TypeScript). The `literature/` package (`pubmed_client`, `retriever`, `synth`, `cache`, `standardize`, `precision`, `config`) does the 5-axis PubMed fan-out, relevance/tier/recency ranking, quality floor, TTL caching, and grounded `[L#]` synthesis; `case_literature.py` attaches it to case sections.

The sole retrieval adapter is **`retrieve.py`** — `build_retriever()` composes a sanitized caseprep FTS5 lane + an in-process `neuro_core.Index.text_search` lane (no-GPU lexical), with a subprocess caseprep CLI fallback, all coerced into `EvidenceRecord` shape.

### P3 — Verification, Grading, Guards, Feedback & Eval (`neuro_caseboard/…` + `eval/` + `evaluation/`)

P3 is the correctness machinery: small, deterministic, mostly stdlib-only guards/graders that run *inside* the engine, plus two large *out-of-engine* evaluation trees. The whole design is conservative — **a gate may only remove a weak citation, never fabricate or re-point one**, and abstains-to-keep when a premise is too thin to judge.

**In-engine guards/graders:**

- **`entailment.py` — the citation entailment gate.** The default `LexicalVerifier` is deterministic and dependency-free: token-overlap recall over the whole premise (`threshold=0.18`) AND precision over the best-matching premise *sentence* (`min_precision=0.2`, `min_premise_tokens=5`). `NLIVerifier` (a lazily-imported `sentence_transformers.CrossEncoder`, MNLI-aware via `id2label`) is used only when env `CASEBOARD_NLI_MODEL` is set and importable, else the system falls back. `should_cite(premise, hypothesis, verifier)` keeps a citation unless a *judgeable* premise is positively rejected (abstain→keep below `min_premise_tokens`); `unsupported_entities` flags cross-source "bleed" via a medical-suffix regex.
- **`answer_verify.py` — post-synthesis claim verification.** `segment_claims` splits an answer into per-sentence `ClaimSpan`s and extracts `[n]`/`[L#]` markers; `verify_answer` joins each claim's cited premises, runs `should_cite` + the bleed check, and returns an `AnswerVerification` (`groundedness()`, `unsupported_markers()`, `bleed_terms()`). `merge_verifications` folds the textbook `[n]` and literature `[L#]` verdicts together; `verification_to_dict`/`verification_notice` produce the API JSON and the human "needs-verification" notice.
- **`evidence_grade.py` — pure classifier.** `GradeSignals(audit_status, n_sources, cited, has_conflict, is_preference) → grade()` returns one of six categories (directly-supported / multi-source / standard-practice / attending-preference / conflicting / unsupported); `summary_bucket` collapses them back to the coarse supported/to-verify axis so existing counts never regress.
- **`guard.prune_offtarget`** — anti-bleed: if the topic carries no posterior-fossa/CPA/skull-base signal it drops cards whose text contains posterior-only anatomy (hand-curated `_POSTERIOR_TERMS`). **`dedup.dedup_sections`** — collapses cross-section near-duplicate claims by Jaccard token-set similarity (`threshold=0.72`), removing later duplicates and leaving an "Also relevant — see &lt;heading&gt;" cross-ref; quarantine-status claims bypass dedup entirely.
- **`feedback.py` + `preferences.py` — the surgeon-in-the-loop.** Marks (`wrong`/`missing`/`important`, persisted JSON) feed `distill()`, which maps them to actions (`wrong→suppress`, `important→elevate`, `missing→add`), keys by `(profile, action, key-terms)`, and accumulates a `weight` + provenance `sources` on re-encounter. `apply_preferences` re-expresses them against a fresh manifest: `suppress` at weight ≥ 2 **removes** matching cards, < 2 only de-emphasizes; `add` injects when absent; `elevate` moves to front. Store: `operative-preferences.json` (override `CASEBOARD_PREFS_STORE`).

**Out-of-engine — `eval/` (the offline gate + live judges):** `quality_gate.py` runs the production engine forced offline/deterministic (`build_case_dossier(use_llm=False)`, fake corpus/canned PubMed, figures off) over the `eval` split and emits ~16 metrics (section/intake/lit/corpus coverage, `attribution_precision`, figure archetype/side/byte-stable/guard-reject, `near_dup_rate`, `red_flag_contamination`); `compare` **fails CI (exit 1) on any regression vs `eval/BASELINE.json`** — which pins nearly every metric at its perfect value, making the gate a zero-regression ratchet. `case_eval`/`coverage`/`intake_eval`/`figure_spec_eval` are the per-workstream deterministic evals; `live_text_judge.py`/`live_image_judge.py` are keyed blind LLM/vision judges (Vertex free, OpenRouter under a hard USD `--budget`) that are explicitly advisory and never block a PR; `monitor/` is a read-only detector loop (build each case K times, flag coverage drops vs baseline with expiring-fingerprint suppression).

**Out-of-engine — `evaluation/` (the benchmark system):** `run_benchmark.py` is a resumable in-process runner over the 67-question "Ask the corpus" manifest (per-question timeout, retry ladder, disambiguation, atomic JSONL append, records `verification`); `finalize_run.py`/`summarize_grades.py` produce human/analysis artifacts; `build_manifest.py`/`validate_manifest.py` enforce verbatim source integrity; `build_failure_ledger.py` turns grades + run rows into a typed defect ledger (`failure-ledger.jsonl`, ~406 records). `gui-council/` drives the live SPA with Playwright + axe-core a11y audits.

### P4 — Output Generation & Rendering (`neuro_caseboard/render_*`, `*_pdf`, `figures_gen/`, …)

P4 turns two P2 models — the evidence-audit `model.Dossier` and the `briefing_model.OperativeBriefingBundle` — into shippable artifacts (Markdown, PDF, Streamlit payloads) and does **no clinical reasoning of its own**. It runs **two parallel renderer stacks**:

- **Offline fpdf2 stack** (`render_pdf.py` for dossiers, `briefing_pdf.render_briefing_clinical_pdf` for Q&A) over `fpdf_base.py`, which embeds DejaVu Unicode fonts with a deterministic `ascii_fallback` (map-replace, e.g. ✓→`[OK]`, then NFKD-strip) that **never emits `?`**. This is the degraded fallback used when Chromium is unavailable; it has a "Neo-Brutalist" look with a standing yellow VERIFY banner footer.
- **HTML→PDF (Playwright/Chromium) stack** (`caseboard_pdf.py`, `briefing_pdf.py`, `operative_briefing_pdf.py`) driven by one token-based print theme (`exec_navy.py`, dark "Signal" default + light "print" variant) mirroring the web theme; `img_data_uri` reroots build-time figure paths to the runtime mount (via `neuro_core.asset_paths`) and inlines them as base64.

`pipeline.render_case_pdf`/`render_ask_pdf` choose Chromium vs fpdf2 from `CASEBOARD_PDF_STYLE` and a Chromium-availability probe (a non-renderer exception is re-raised, not masked). The **operative briefing** renderer is the most intricate piece: a *fit ladder* (`fit_briefing_page`) shrinks font → trims optional content → does one LLM `compress` pass → allows a page 2 (critical content never dropped) to hold page 1 to ≤2 pages, using PyMuPDF for the authoritative page count and sharing one `_pdf_bytes` primitive between measurement and final render so the optimized page count is **byte-identical** to the shipped PDF. Every page-1 visible string is routed through `_vis()` to strip leaked citation markers — a hard "no visible citations on page 1" invariant.

**Figure presentation:** `captions.py` reassembles full figure captions from page text and emits subspecialty-neutral relevance lines (fabricating no clinical content); `briefing_figures.py` selects 5–10 high-yield plates by round-robin over pathology/anatomy/technique/device intents. The **generated-schematic lane** (`figures_gen/`) is fully deterministic: `author.py` (LLM-first or a topic-agnostic deterministic fallback) emits a `FigureSpec`, `guard.py` rejects specs whose side/level/region contradict the case (reusing `neuro_core.figure_guards`), and `render.py` (PIL) draws a byte-identical PNG with a mandatory "SCHEMATIC — NOT A RADIOGRAPH" banner and collision-avoiding labels; for `anatomy_map` archetypes with a retriever, `plate.py` substitutes an annotated real textbook plate (with a "REFERENCE PLATE — NOT THIS PATIENT'S IMAGING" banner) instead. `board_view.py` is a pure presenter adapting a Dossier into the Streamlit Build payload (strips inline image embeds `st.markdown` can't resolve, de-dups figures).

### P5 — Interfaces, Surfaces & Deployment

Four surfaces all forward to the *same* engine entry points: the **`caseboard` CLI** (`cli.py`: ask/build/case/cards), the **FastAPI wrapper** (`api/server.py`: JSON-serializes `QAResult`/`Dossier`/`OperativeBriefingBundle`, serves whitelisted figures, exposes an honest `/api/health` probe, and serves the built React SPA from one process), the **React/Vite SPA** (`web/`: `lib/api.ts` talks to the API through a same-origin `/api` proxy and forwards the `kind` discriminator rather than throwing), and the **legacy Streamlit app** (`app/`: reuses the engine + P4 `board_view`). Phone access is uvicorn bound to `0.0.0.0:8001` (`serve_phone.py`/`serve-phone.sh`) with WSL2 port-proxy/Cloudflare-tunnel helpers in `scripts/`. The browser briefing contract `web/src/lib/briefingTypes.ts` is **generated** from P2's Pydantic schema by `scripts/gen_briefing_types.py` and drift-guarded by a pytest. CI (`.github/workflows/ci.yml`+`web.yml`) is offline pytest + web lint/vitest/build + a quality gate; CD builds a multi-stage Docker image to GHCR consumed by a pull-based rollout with engine-health rollback.

---

## 4. End-to-end data flow

### A single Case-prep request (dictation → rendered briefing)

1. **Input** arrives at a surface — e.g. `cli._run_case` or `POST /api/briefing` (P5) — and calls `pipeline.build_briefing_bundle(...)` (P2).
2. **Intake**: `intake.parse_dictation` (LLM-first + deterministic geometry floor) produces a `CaseContext` (`case_context.py`).
3. **Manifest**: `case_author.build_case_manifest` authors `QuestionCard`s across the 8 `case_sections.py` surfaces.
4. **Guard**: the manifest passes through `guard.prune_offtarget` [P3] and `preferences.apply_preferences` [P3].
5. **Retrieve**: `retrieve.build_retriever` (P2) wraps the P1 `neuro_core.Index.text_search` lexical lane (+ caseprep FTS5) and `figure_retriever`, returning `EvidenceRecord`s; caseprep `enrich_manifest` attaches them as `.papers`.
6. **Audit**: caseprep `audit_manifest` stamps each card `audit_status` (supported / needs_review / no_evidence / off_target).
7. **Compile**: `compile.compile_case_dossier(verifier=get_default_verifier)` (P2) groups cards, gates inline `[n]` citations via `entailment.should_cite` [P3] (withholding → `claim.status="verify"`, never fabricating), grades claims via `evidence_grade.grade` [P3], collapses duplicates via `dedup.dedup_sections` [P3], completes captions via `captions` [P4], and emits a `model.Dossier`.
8. **Literature (additive)**: `case_literature.attach_case_literature` attaches synthesized PubMed `[L#]` paragraphs; any failure leaves `section.literature = None`.
9. **Briefing synthesis**: `briefing_synth.gather_briefing_evidence` pools T#/L# sources, `synthesize_briefing` fires 7 concurrent section LLM calls parsed into the `briefing_model.OperativeBriefing`, `briefing_figures.select_briefing_figures` [P4] picks plates → an `OperativeBriefingBundle`.
10. **Render**: `pipeline.render_case_pdf` selects `caseboard_pdf`/`operative_briefing_pdf` [P4] (Chromium, fpdf2 fallback); the API instead emits `bundle.model_dump(mode='json')` and the SPA renders it.

### Corpus ingestion → index (build time)

`neuro_core/scripts/build_index.py` globs `CORPUS_DIR/*.pdf` → `ingest.extract_pages` (PyMuPDF) classifies the TOC, **drops appended non-medical contamination** (the David-Icke-on-Youmans case), assigns chapter labels, detects figures by raster-area fraction, and crops per-plate PNGs to `ASSETS_DIR/<book>/p<NNNN>_f<II>.png`. `chunk.chunk_pages` slices text into overlapping windows; `embed.Embedder` (BGE) encodes them; `index.build_index` writes `chunks.lance` + FTS. Then `build_visual_index` embeds plates with BiomedCLIP into `figures.lance`; `recaption_figures` later adds a `gemini_caption` column. `build_cards_index` ingests an external Anki deck into `cards.lance`. `probe_book` gates scanned PDFs (text coverage < 0.6, no OCR); `purge_contamination` audits/removes contaminated rows post-build.

---

## 5. Cross-cutting seams

- **Retrieval adapter (P1↔P2):** `neuro_caseboard/retrieve.py` is the *sole* adapter. It imports `neuro_core.Index.text_search`, `figure_retriever.build_figure_retriever`, `config.load_config`, `asset_paths.resolve_asset_path`, wrapping them into `InProcessTextbookRetriever` (+ subprocess fallback) emitting `EvidenceRecord`s. `qa.py` separately calls `neuro_core.query()`/`plan_retrieval()` and consumes `QueryResult`/`RetrievalBundle`/`Clarification`; `woven_synth.py` re-imports P1's `synthesize` formatters and `Citation`.
- **Domain-model hub (P2 owns; P3/P4/P5 read):** `model.Dossier` and `briefing_model.OperativeBriefingBundle` (+`BRIEFING_SCHEMA_VERSION`). P4 renderers walk them (and never construct them); `api._dossier_dict` + `model_dump(mode='json')` serialize them; `scripts/gen_briefing_types.py` reads the JSON schema into `web/src/lib/briefingTypes.ts`.
- **Verification/guard fan-out (P2/P5↔P3):** `compile`+`pipeline`+`qa` and `api/server.py` call `entailment.get_default_verifier`, `answer_verify`, `dedup`, `guard.prune_offtarget`, `evidence_grade`. Invariant: citations withheld, never fabricated.
- **Presentation helpers (P2→P4 calls):** `compile.py` imports P4's `captions.complete_caption`/`relevance_line`; `retrieve.py` imports `captions.assemble_caption`; `pipeline.build_briefing_bundle` imports `briefing_figures.select_briefing_figures` — P4 supplies presentation functions called from the orchestrator.
- **Surgeon-in-the-loop (P5→P3→P2):** `POST /api/feedback` → `feedback.CaseFeedback` → `preferences.distill/save` → `pipeline.build_dossier` rebuilds with prefs applied (and re-caches so a later PDF matches what the surgeon now sees); `tests/rehearsal/` exercises it.
- **Figure dual-lane:** retrieved plates (P1 `figure_retriever`/`figure_guards`) vs. generated schematics (P4 `figures_gen`), both surfacing into the rendered dossier/briefing and the web/Streamlit figure grids; `figures_gen/guard.py` reuses `neuro_core.figure_guards.figure_offtarget`.
- **Eval/monitor (P3 drives P1/P2):** `eval/`+`evaluation/` execute the live engine and consume internals (`dedup`, `case_literature`, attribution precision, `render_md`) to detect regressions; `gui-council/` drives the P5 web surface.

---

## 6. External dependencies & services

- **LLMs:** The **Ask** synthesis lane defaults to **OpenRouter `z-ai/glm-5.2`** (best blind-graded answer quality), with query disambiguation on a separate fast model, **OpenRouter `google/gemini-3.1-flash-lite`** (`ANALYZE_MODEL`); set `SYNTH_PROVIDER=vertex` to revert Ask synthesis to free Vertex Gemini (`gemini-2.5-pro`). **Build/Case and the operative briefing stay on Vertex AI Gemini** (`google-genai`, ADC + `GOOGLE_CLOUD_PROJECT`): the Explorer (`CASEBOARD_LLM_PROVIDER=vertex`) uses `gemini-2.5-pro` and the 7 briefing section calls use `gemini-2.5-flash`. Local Ollama is a further alternate; all backends sit behind a uniform `.generate`.
- **Vector store:** LanceDB (vector kNN + Tantivy FTS, RRF-fused) backing `chunks`/`figures`/`cards` tables in one `INDEX_DIR`.
- **Embeddings/rerank:** sentence-transformers BGE-large-en-v1.5 + bge-reranker-v2-m3; BiomedCLIP via open_clip for figures. PyTorch + optional CUDA (CPU fallback). The container needs `libgomp1`.
- **PDF/figures:** PyMuPDF (extraction/cropping + authoritative briefing page count), Pillow (deterministic schematics), fpdf2 (offline PDF), and Playwright/Chromium for HTML→PDF. DejaVu Sans TTFs embedded for Unicode glyphs; DM Sans / Space Mono `@import`-ed in the HTML theme.
- **PubMed:** NCBI E-utilities via httpx (rate-limited, `NCBI_API_KEY`), with on-disk TTL caching.
- **Deployment:** Docker multi-stage → GHCR; docker-compose single-process serve (corpus/index/figures/ADC mounted read-only); Cloudflare quick tunnel + WSL2 netsh port-proxy for phone access.
- **File formats:** PDF in; PNG figure plates; LanceDB/Arrow index; JSONL (caption checkpoints, eval manifest/run/grades/ledger); persisted JSON for feedback/preferences/cache/baselines.

---

## 7. Entry points & surfaces

- **CLI** (`caseboard`, `pyproject` `[project.scripts]`): `ask` → `qa.answer_question` (+`--pdf`); `build`/`case` → `pipeline.generate`/`generate_case` (`--no-llm`, `--no-enrich`, `--no-literature`, `-o`); `cards` → `neuro_core.cards_query`.
- **FastAPI** (`api/server.py`, port **8001**): `/api/ask|build|build/pdf|briefing|briefing/pdf|feedback|cards|figure|health|preferences`. Deliberately **auth-free** (local-first); serves `web/dist` via a catch-all that never shadows `/api/*`. `serve_phone.py` binds `0.0.0.0`. The briefing PDF endpoint serves the **cached** bundle (a cache miss is a 404, never a silent rebuild).
- **React SPA** (`web/`): Vite dev on `:5173` proxying `/api` to `:8001`; built bundle served by FastAPI in prod. `lib/api.ts` decodes the `kind` discriminator instead of throwing.
- **Streamlit** (`app/streamlit_app.py`): the *only* surface with a password gate (`APP_PASSWORD`); reuses the engine + P4 `board_view`.
- **Docker/dev:** multi-stage image (`CMD uvicorn api.server:app 0.0.0.0:8001`, `HEALTHCHECK /api/health`); `dev.sh` runs uvicorn `--reload` + vite concurrently.

---

## 8. Notable observations, risks & open questions

**Confirmed design facts / risks:**

- **Stale config default (one, and harmless).** `config.DEFAULTS['CORPUS_DIR']='/mnt/d/textbook_pdfs'` vs. the live `/home/michael/textbook_pdfs` — but `CORPUS_DIR` is read only at index-build time, never on the query/Ask path (which uses `INDEX_DIR`/`ASSETS_DIR`, both defaulting correctly), so it is merely misleading. The synthesis defaults are **current**: `config.DEFAULTS` now selects `SYNTH_PROVIDER=openrouter` + `OPENROUTER_MODEL=z-ai/glm-5.2` + `ANALYZE_MODEL=google/gemini-3.1-flash-lite`. Env/`.env` override any literal.
- **Process-wide singletons.** `get_engine`/`_load_rows`/`_ROWS_CACHE` are keyed only on first call — a second call with a different `Config` is silently ignored. Fine for one-process surfaces, a latent gotcha for in-process re-config or test isolation.
- **Duplicated guard logic.** `neuro_core/figure_guards.py` copies region-guard symbols *verbatim* from caseprep "to keep neuro_core dependency-clean"; `figures_gen/guard.py` (P4) in turn imports `neuro_core.figure_guards` lazily and **degrades silently** (to "no shared levels"/"pass region") if that import fails — a deliberate copy/coupling that risks drift if only one side is edited.
- **`evidence_grade` conflict/preference categories are reachable but unwired.** `compile.py` passes only `audit_status`/`n_sources`/`cited` to `GradeSignals`, so `has_conflict`/`is_preference` default `False` — the `conflicting` and `attending-preference` grades exist in the classifier but their provenance is **not yet threaded** from compile (an acknowledged in-code TODO).
- **Two divergent PDF visual identities by design.** The fpdf2 fallback (`render_pdf`, "Neo-Brutalism") and the Chromium HTML stack (`caseboard_pdf`/`briefing_pdf`/`operative_briefing_pdf` via the `exec_navy` "Signal" theme) are not unified — so a CI-rendered (no-Chromium) PDF looks **materially different** from the shipped one. Glyph integrity, though, is genuinely guaranteed (`ascii_fallback` can never emit `?`), and missing-asset/dark-mode handling is robust (every image embed is try/except'd to caption-only).
- **Operative-briefing `_CITE_MARKER` over-stripping risk.** On page 1 the citation-marker regex strips bracketed bare-digit groups like `[3]`; a clinical value rendered as a lone bracketed integer would be removed (multi-token brackets like `[3 mm]`/`[Grade II]` survive). Low-likelihood, worth a test — verified by reading the regex, not run against live synth output.
- **`BASELINE.json` is a zero-regression ratchet.** Nearly every offline `min` metric is pinned at 1.0 and `near_dup_rate`/`red_flag_contamination` at 0.0, so any drop fails CI; `LIVE_BASELINE.json` is advisory and never blocks a PR. `NEURO_CASEBOARD_EVALUATION.md` is candid that its +1.62 benchmark delta is run-to-run LLM/grader noise and the only real deliverable is the test-proven empty-answer reliability guard — consistent with "validate by output, not retrieval counts."
- **Determinism of generated schematics is load-bearing.** `render_spec` fixes palette/layout and writes PNGs with no timestamp, so the same `FigureSpec` is byte-identical (CI can diff renders); the figure-spec eval asserts byte-stability and that the guard rejects side-flips.
- **Seam-tracker correction (from P2).** `model.py` does **not** import `evidence_grade`; only `compile.py` does. `model.py` declares `Claim.grade` as a plain string.
- **Auth nuance (from P5).** The FastAPI surface is intentionally **auth-free**; the password gate lives only in Streamlit. Phone exposure relies on network reachability, not a password.
- **Two build entry points.** CLI uses `pipeline.generate`/`generate_case`; API/Streamlit use `build_dossier`/`build_case_dossier`/`build_briefing_bundle` — sibling wrappers (P2-confirmed).
- **Exported≠displayed asymmetry.** `briefing_pdf` serves only the *cached* bundle (404 if absent) because the 7-call synthesis is nondeterministic, but `build/pdf` will *rebuild* on a cache miss — so a Build PDF after cache eviction can differ from what was shown.
- **Geometry deliberately dropped from PubMed queries** (`case_literature.section_query`) because PubMed ANDs every token and geometry collapsed recall to zero (live observation: 0 vs. 8 records).
- **Fragility hotspot:** `briefing_synth.py` carries battle-tested marker-parsing complexity (`{T1}`/`[T1]`, §11 scrubbing) driven by named regressions — brittle if the section grammar changes.
- **Machine-specific constraints:** port 8001 (not 8000) everywhere to dodge a Windows WinNAT excluded range on this WSL2 host; `scripts/batch_ask.py` hardcodes Windows-mount paths (a personal one-off, untracked).

**Open questions / not independently runnable:**

- P1 could not verify live LanceDB row counts/dimensionality (schema inferred from build code); `books.lance`/`meta.lance` exist in the live index but no read path writes them — likely legacy from the predecessor textbook-rag repo, producer/consumer unverified.
- P2 could not confirm the caller of `topic_extract.extract_board_topic` (likely a P5 "board-from-an-ask" path).
- P3's keyed live-judge numbers and the ~406-row failure ledger are credentialed/historical artifacts — read via their generators/schemas (data-shape contracts confirmed) but not re-executed offline. The benchmark runner's per-question timeout cannot kill a runaway worker thread (documented limitation).
- P4's actual Chromium/fpdf2 rendering fidelity and font-embedding success were read from source/tests, not executed on this box.
- Scanned PDFs remain the known #1 failure mode: the pipeline does not OCR, so indexing a scanned book past the `probe_book` gate silently yields empty chunks.
