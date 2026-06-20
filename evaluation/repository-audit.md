# Neuro·Caseboard Repository Audit — "Ask the corpus" / `/ask`

Audit date: 2026-06-20. Scope: this worktree only
(`/home/michael/PROJECTS/neuro-caseboard/.claude/worktrees/session-2026-06-20-1253`), no external
sources. Purpose: tell the 67-question benchmark runner exactly **how to invoke `/ask`
programmatically**, how to start the API, and whether a real baseline run is currently possible.

Convention: **FACT** = verified by reading code / running a probe in this repo (cited `path:symbol`
or `path:line`). **HYPOTHESIS** = inference not directly proven. Line numbers are from the files as
they exist in this worktree.

---

## Executive summary

**Preferred programmatic path: an in-process Python call — no HTTP, no browser.**

- **FACT.** The browser endpoint `POST /api/ask` (`api/server.py:ask`, line 332-368) does nothing but
  call one engine function and serialize the result:
  `result = answer_question(question, force=req.force)` (`api/server.py:343`). `force` defaults to
  `True` (`api/server.py:AskRequest.force`, line 270).
- **FACT.** That function is `neuro_caseboard/qa.py:answer_question(question, *, config=None,
  force=False, lane_a=None, lane_b=None)` (line 103). It returns a `QAResult`
  (`qa.py:QAResult`, line 33-38: `answer`, `citations`, `figures`, `literature`) **or** a
  `neuro_core.query.Clarification` (`neuro_core/query.py:35`) when the question is ambiguous.
  Calling it directly yields the **same answer object** the UI renders — the route adds only JSON
  field-shaping, not synthesis.

**Recommended runner invocation (in-process):**

```python
from neuro_caseboard.qa import answer_question        # qa.py:103
from neuro_core.query import Clarification            # query.py:35

result = answer_question(question, force=True)
if isinstance(result, Clarification):
    # disambiguation: result.question, result.variants[].label / .rewrite
    # to mirror the questioner protocol, re-call with a chosen variant's rewrite:
    result = answer_question(result.variants[i].rewrite, force=True)
# else: result.answer (str), result.citations (list[Citation]),
#       result.figures (list[Figure]), result.literature (LiteratureSection|None)
```

Capture per question: `result.answer`; `result.citations` (each
`neuro_core/synthesize.py:Citation` → `n, book, chapter, page`); `result.figures` (each
`neuro_core/query.py:Figure` → `source_n, book, chapter, page, image_path, caption`);
`result.literature` (`qa.py:LiteratureSection` → `narrative`, `citations[]` of PubMed records).

If byte-identical UI JSON is required instead, hit `POST http://127.0.0.1:8001/api/ask` with
`{"question": "...", "force": true}` — same engine call, plus the serializers in `api/server.py`
(`_citation_dict` L282, `_figure_dict` L295, `_literature_dict` L312).

**Baseline-blocking dependencies — ALL currently satisfied (a REAL baseline run is possible now):**

| Dependency | Required for | Status (probed 2026-06-20) | Evidence |
|---|---|---|---|
| Vertex synthesis (`SYNTH_PROVIDER=vertex` + `GOOGLE_CLOUD_PROJECT` + ADC + `google.genai`) | the LLM answer | **AVAILABLE** | `_probe_synth()` → `{"available": true, "provider":"vertex", "project":"project-a20782b0-…", "adc":true, "client_import":true}` |
| LanceDB index at `INDEX_DIR` (`chunks.lance`) | retrieval | **AVAILABLE** | `_probe_corpus()` → `available:true`, `index_dir=/home/michael/neuro-textbook-rag/index`; `chunks.lance` present on disk |
| Cards table (`INDEX_DIR/cards.lance`) | `/api/cards` lane only (not `/ask`) | available | `_probe_cards()` → `available:true` |
| NCBI key (literature Lane B) | optional enrichment of `/ask` | enabled, key present | `_probe_literature()` → `{"enabled":true,"ncbi_key":true}` |

**How to detect blockage programmatically:** call `api/server.py:health()` (or its helpers
`_probe_synth`/`_probe_corpus` directly, lines 77-126) — top-level booleans `synth` and `corpus`
must both be `true` before a real baseline. The runner should assert these and abort with an honest
"baseline not runnable" rather than recording fabricated/degraded answers.

**Caveat (HYPOTHESIS / operational):** `GOOGLE_CLOUD_PROJECT` was found in the **process
environment** (`project-a20782b0-…`), **not** in `.env` (grep of `.env` returned nothing). The
runner process must inherit that env var (or it must be added to `.env`), or `_probe_synth` will
report `missing: GOOGLE_CLOUD_PROJECT` and synthesis will fail. This is the single most likely
"works in my shell, fails in the runner" trap.

---

## 1. The `/ask` request path, end-to-end

**Framework: FastAPI.** **FACT** — `api/server.py:42` `app = FastAPI(...)`; route decorators
`@app.post("/api/ask")` (L332), `@app.get("/api/health")` (L164), etc. CORS middleware allows only
the Vite dev origins (`api/server.py:47-55`). No auth/passcode gate on this surface
(`api/server.py` module docstring, L3-4).

Trace **frontend → API → engine**:

1. **Frontend.** SPA route `/ask` is the built React/Vite app served by the FastAPI catch-all
   `_serve_spa` (`api/server.py:688`). The browser path the questioner protocol drives
   (`http://127.0.0.1:8001/ask`) is client-side routing; the actual data call is `POST /api/ask`.
   **HYPOTHESIS** (web source not exhaustively read): the React Ask page POSTs `{question}` to
   `/api/ask` and renders `kind` ∈ {`answer`,`clarification`,`unavailable`,`error`}.
2. **API route.** `api/server.py:ask(req: AskRequest)` (L332). Request schema
   `AskRequest{question: str, force: bool=True}` (L266-270). Empty question → 422 (L335-336).
3. **Engine call.** `result = answer_question(question, force=req.force)` (L343), importing
   `from neuro_caseboard.qa import answer_question` (L340).
4. **Response shaping.** On `Clarification` → `{"kind":"clarification","question","variants":[{label,
   rewrite}]}` (L352-360). On success → `{"kind":"answer","answer","citations":[…],"figures":[…],
   "literature":…}` (L362-368) via `_citation_dict`/`_figure_dict`/`_literature_dict`.

**Importable entrypoint producing the SAME answer object: YES.** **FACT** —
`neuro_caseboard/qa.py:answer_question` (L103) is exactly what the route calls. The route adds **no**
synthesis logic; it only converts dataclasses to dicts and maps exceptions to HTTP codes. So an
in-process call is equivalent at the answer/citation/figure level.

**Response/object schema (in-process):**
- `qa.py:QAResult` (L33): `answer: str`, `citations: list[Citation]`, `figures: list[Figure]`,
  `literature: LiteratureSection|None`.
- `neuro_core/synthesize.py:Citation` (L36): `n: int, book: str, chapter: str, page: int`.
- `neuro_core/query.py:Figure` (L17): `source_n, book, chapter, page, image_path, caption`.
- `qa.py:LiteratureSection` (L27)/`LiteratureCitation` (L16): PubMed `narrative` + `[{n,pmid,title,
  journal,year,doi,url}]`.
- `neuro_core/query.py:Clarification` (L35): `question: str`, `variants: list[VariantRewrite]`
  (`query_analyze.py:VariantRewrite` → `label`, `rewrite`).

Real synthesis work is done in `neuro_core/synthesize.py:synthesize` (L88) which calls
`synth_client.generate(SYSTEM_PROMPT, user, images)` (L95). Lane A retrieval+synthesis lives in
`neuro_core/query.py:Engine.query` (L219) → `_answer` (L204).

---

## 2. Starting the app / minimal command on 127.0.0.1:8001

**FACT.**
- Canonical: `uvicorn api.server:app --port 8001` (documented in `api/server.py` docstring, L19/L25).
  By default uvicorn binds `127.0.0.1`, which is exactly the protocol's
  `http://127.0.0.1:8001`.
- Phone/LAN launcher: `scripts/serve-phone.sh [PORT]` builds the SPA if missing then
  `exec python3 -m api.serve_phone --port "$PORT"` (default 8001). `api/serve_phone.py:main` (L175)
  binds `--host 0.0.0.0` by default (`DEFAULT_PORT=8001`, `APP="api.server:app"`, L12-13) via
  `os.execvp` of `python -m uvicorn` (`uvicorn_argv`, L53-59).

**Minimal command to bring up the API on 127.0.0.1:8001 (no SPA build needed for the API):**
```
uvicorn api.server:app --host 127.0.0.1 --port 8001
```
(If `web/dist` is absent, only `/` returns an honest 503; all `/api/*` endpoints still work —
`api/server.py:_serve_spa`, L697-703.)

**Note for the runner:** because `answer_question` is importable, the runner can skip starting any
server entirely and call the engine in-process (see §13). Either way set
`PYTHONPATH=<worktree>:<worktree>/vendor/caseprep` so this worktree's code (not the editable main
checkout) is authoritative, and run with `python3`.

---

## 3. Retrieval & ranking pipeline

**FACT — hybrid (vector + BM25/FTS) with Reciprocal Rank Fusion, then cross-encoder rerank.**
- `neuro_core/index.py:Index.hybrid_search(query_text, query_vector, k)` (L116): runs
  `vector_search` (LanceDB ANN on `vector` column, L108) **and** `text_search`
  (`query_type="fts"`, LanceDB full-text/BM25, L112), then fuses with
  `reciprocal_rank_fusion` (L22, RRF constant `k=60`) and returns top-`k` `Hit`s with the fused
  `score`.
- Table name: `chunks` (`index.py:TABLE`, L6); FTS index built on `text` (L89).
- `Engine._retrieve` (`query.py:172`): embed query (`Embedder.embed_query`), `hybrid_search(...,
  config.retrieve_k)`, then `Reranker.rerank(question, hits, config.rerank_k)`.
- Reranker: `neuro_core/rerank.py:Reranker.rerank` (L19) — `sentence_transformers.CrossEncoder`
  (default `BAAI/bge-reranker-v2-m3`), sorts by score desc, returns top-`rerank_k`, overwrites
  `hit.score` with the cross-encoder score.
- Defaults: `RETRIEVE_K=40`, `RERANK_K=12`, `EMBED_MODEL=BAAI/bge-large-en-v1.5`
  (`neuro_core/config.py:DEFAULTS`, L8-24). Embedding device `auto` → cuda if available else cpu
  (`config.py:resolve_device`, L52).

Score fields: hybrid RRF `score` on `Hit` (`index.py:Hit.score`), overwritten by cross-encoder
score after rerank. No score is surfaced in the `/api/ask` JSON (citations carry location only).

---

## 4. Figure / image retrieval lane

**FACT.** Implemented in `neuro_core/query.py:Engine._collect_figures` (L97). Three sub-lanes fused
by RRF on `figure_path`:
1. **Text-figure hits** — reranked passages where `has_figure and figure_path` (L103).
2. **Visual lane** — `_visual_hits` (L71): BiomedCLIP image embedding
   (`VisualEmbedder`/`VisualIndex`, `config.visual_model`, `VISUAL_RETRIEVE_K=10`,
   `VISUAL_RETRIEVAL=true`). Wrapped in try/except — a failure degrades to text-only (L78-81).
3. **Caption lane** — `_caption_hits` (L83): lexical search over each figure's Gemini caption
   (`build_figure_retriever`, `CAPTION_RETRIEVAL=true`, `CAPTION_RETRIEVE_K=10`).

Each lane deduped by `figure_path` before fusion (L121-125), then an **off-target region guard**
`neuro_core/figure_guards.py:figure_offtarget(cap, question, book, guards="strict")` filters
cross-region plates (L149). Capped at `config.max_figure_images` (`MAX_FIGURE_IMAGES=5`). Citation
source numbers assigned by reusing a passage's number if the figure's page is already cited, else
appending (`passage_index`, L127-133, `next_appended`). Unreadable PNGs dropped from both figure and
image lists (`_read_image`, L164). Images are passed as bytes to the LLM for multimodal description.

Serving: figures come back as **absolute local paths**; the API exposes them via
`GET /api/figure?path=<abs>` with a whitelist guard (`api/server.py:figure` L251,
`_safe_image_path` L226 bounded to `_image_roots()` L202). The in-process runner gets the raw
`image_path` directly on each `Figure`.

---

## 5. Prompt assembly

**FACT.** `neuro_core/synthesize.py`.
- System prompt: `SYNTHESIZE.SYSTEM_PROMPT` (L8-20) — "neurosurgical reference assistant; answer
  ONLY from provided passages/images; cite bracketed source number `[n]` for every clinical claim;
  emit the verbatim refusal string if not found".
- Refusal sentinel: `REFUSAL = "Not found in the provided sources."` (L6), checked by
  `is_refusal` (L23) — single source of truth shared by prompt and detector.
- User message assembly: `synthesize` (L88) → `_format_passages` (L49, numbers passages `[i]
  book, chapter, p.page`), `_format_appended` (L74, figure-only sources), `_figure_note` (L60,
  maps attached images to source numbers), plus optional `variant_directive` for disambiguation.
- Variant directive text: `neuro_core/query.py:_variant_directive` (L50).

No prompt-template files or prompt hashes found. **HYPOTHESIS**: prompts are inline string constants
only (`SYSTEM_PROMPT`, `ANALYZE_SYSTEM_PROMPT`); no versioned/hashed prompt registry exists. The
disambiguation prompt is `neuro_core/query_analyze.py:ANALYZE_SYSTEM_PROMPT` (L83).

---

## 6. Citation generation & validation

**FACT.** Citations are generated **deterministically from the retrieved passages**, not parsed from
the LLM text. `neuro_core/synthesize.py:synthesize` (L96-102) builds one `Citation(n=i, book,
chapter, page)` per reranked passage `i`, plus appended figure-only citations. So citation
**numbers map 1:1 to the numbered passages handed to the model** — the `[n]` markers in the answer
reference those passages by construction.

**Validation is by-construction, not post-hoc verification.** **FACT** — there is no step that
parses the answer's `[n]` markers and checks each against its passage. The one guard: on a **refusal**
(`is_refusal`, synthesize.py:23) the engine **drops all citations and figures** because they would be
spurious (`query.py:_answer`, L209-212). **HYPOTHESIS**: the model could still cite a number it
wasn't given or mis-attribute a claim; nothing in this path detects that. (The web layer adds
provenance *classification* of markers — textbook/literature/card — in `web/src/lib/provenance.ts`,
asserted by `tests/test_citation_provenance.py`, but that is display provenance, not factual
verification.)

---

## 7. Corpus & metadata stores

**FACT.** LanceDB at `INDEX_DIR` (`/home/michael/neuro-textbook-rag/index`). Tables present on disk:
`chunks.lance` (queryable text+vector, `index.py:TABLE="chunks"`), `cards.lance` (board-review
cards), `figures.lance`, `books.lance`, `meta.lance`, plus `_gemini_captions.jsonl` and a
`__manifest` dir. The `chunks` row schema (`index.py:build_index`, L70-80): `id, book, chapter,
page, text, vector, has_figure, caption, figure_path`.

- **Cards** table lives **inside** `INDEX_DIR/cards.lance` (queried by `neuro_core/cards_query.py`,
  surfaced at `/api/cards`); `CARDS_SOURCE_DB` is only the source deck to *build* it
  (`api/server.py:_probe_cards`, L129-145). Cards are a separate lane — **not** part of `/ask`.
- **Fingerprinting / incremental build options:** `index.py:build_index(mode=...)` supports
  `"overwrite"` (default) and `"append"` (idempotent per-book replace via `_replace_books`, L44,
  then `optimize()`); raw PDFs in `CORPUS_DIR` are needed only to (re)index, not to query
  (`api/server.py:_probe_corpus` docstring, L112-114). For reproducibility, the evaluation framework
  records a "corpus fingerprint" per run (`evaluation/README.md`, "Reproduction").

---

## 8. Model / provider configuration & env vars

**FACT.** Provider selection: `neuro_core/synth_clients.py:make_synth_client(config)` (L107) →
`local` → `LocalSynthClient`; `openrouter` → `OpenRouterSynthClient`; **else → `VertexSynthClient`**
(default). Vertex client (L69-104) uses `google.genai` with `vertexai=True`, ADC auth, model from
`config.vertex_model`, `temperature=0.1`, multimodal (text + PNG bytes).

Config (`neuro_core/config.py:DEFAULTS`, L5-49; resolved by `load_config`, L116):
- `SYNTH_PROVIDER` default **`"vertex"`** (L25) — **note: the default is NOT stale** in this
  worktree (CLAUDE.md warns of a stale Anthropic default; the live `DEFAULTS` already say `vertex`).
- `GOOGLE_CLOUD_PROJECT` default `""` (must be supplied via env or `.env`), `GOOGLE_CLOUD_LOCATION`
  `us-central1`, `VERTEX_MODEL` `gemini-2.5-pro`.
- `GPU_GUARD=true`, `GPU_MIN_FREE_MIB=10000` — but the GPU guard only runs when
  `synth_provider == "local"` (`query.py:query`, L262). **Under Vertex the GPU guard is bypassed**,
  so a Vertex baseline will not raise `GpuNotReadyError` from synthesis. (The reranker/embedder may
  still use GPU if available, but that's `auto`/cpu-capable.)
- `OPENROUTER_MODEL` default `anthropic/claude-sonnet-4.6` is only used if provider is switched to
  openrouter — **not** this deployment.

Env loading: `load_config` reads `os.environ` first, then `.env` (`_parse_env_file`, L63), then
`DEFAULTS` (`get`, L119-124). The literature lane has its own `.env` auto-loader
(`neuro_caseboard/literature/config.py`, per CLAUDE.md). **Probed live:** `synth_provider=vertex`,
`project=project-a20782b0-…`, ADC present, `google.genai` importable → synthesis **AVAILABLE**.

---

## 9. Disambiguation behavior ("maps to several distinct topics — pick the variant")

**FACT.** Two-stage, in `neuro_core/query.py:Engine._plan_query` (L177) + `neuro_core/query_analyze.py`.
1. **Cheap gate (no LLM):** `query_analyze.py:ambiguity_gate(question, hits)` (L63). Trips when the
   question names an ambiguous parent procedure from the curated taxonomy `VARIANT_AXES` (L18 —
   decompressive-craniectomy, anterior-cervical, pterional-approach, csf-diversion) **or** retrieved
   passages name ≥2 variants of one axis.
2. **LLM analyze (one pass):** if gate trips, `query_analyze(question, top, synth_client)` (L146)
   runs `ANALYZE_SYSTEM_PROMPT` (L83) returning JSON `{ambiguous, axis, variants[{label,rewrite}],
   chosen, confidence}`. Fail-open: any error → `ambiguous=False` (L154-155), so the normal answer
   always stands.

**Trigger for returning a clarification vs. auto-resolving** (`_plan_query`, L182-191):
- gate not tripped, or `analysis.ambiguous=False` → answer normally.
- ambiguous **and** `confidence < CLARIFY_THRESHOLD (0.6)` (`query_analyze.py:81`) → **return
  `Clarification`** (ask the user; **no answer/figures produced**).
- ambiguous **and** `confidence >= 0.6` → silently resolve to `analysis.chosen.rewrite`, re-retrieve,
  and prefix the answer with `**Assuming <label> (most consistent with retrieved sources).**`
  (`query.py:_answer`, L214-216).

**What the API returns** (`api/server.py:ask`, L352-360): `{"kind":"clarification","question":…,
"variants":[{"label":…,"rewrite":…}]}`. **Runner implication:** to honor the questioner protocol
("pick the most clinically comprehensive option, note the variant"), the runner re-submits the
chosen `variant.rewrite` as a fresh `answer_question(...)` call and records which label it chose.
There is **no** parameter to pre-select a variant in one call.

---

## 10. Error handling & the "Engine error" surface

**FACT** (`api/server.py:ask`, L342-350):
- `GpuNotReadyError` → HTTP **503** `{"kind":"unavailable","reason":"GPU not ready: …"}`. (Only
  reachable under `synth_provider=local`; not under Vertex.)
- Any other `Exception` → HTTP **500** `{"kind":"error","error":"<Type>: <msg>"}`. **This is the
  "Engine error" the questioner protocol retries on.** A Vertex API failure, a LanceDB read error, or
  a model load error surfaces here.
- Empty question → **422** `{"kind":"error","error":"empty question"}`.

**Runner implication:** in-process, these become a raised Python exception (for the 500 class) — the
runner should wrap `answer_question` in try/except, record the exception type+message as an
ENGINE-ERROR result, and apply the protocol's retry ladder (immediate → 30s → log-and-skip). Lane B
(literature) failures never raise into the answer — they are swallowed to `literature=None`
(`qa.py:99`, L126-130).

---

## 11. Logging / telemetry (provenance, observable fallback — PR #41)

**FACT.** Logging is via stdlib `logging`. Lane B failures: `qa.py:_log.debug("literature lane
failed", exc_info=True)` (L99, L129). LLM-explorer degradation is logged at WARNING/DEBUG in
`neuro_caseboard/explore_llm.py` (L432-443) with an "honest degradation" docstring (L20).

**PR #41 "Observable LLM fallback — provenance + honest degradation (backend)":** the `/api/health`
probes (`api/server.py:_probe_synth/_probe_corpus/_probe_cards/_probe_literature`, L77-161) are the
observable-degradation surface — they report *what is and isn't available and why* (`detail`
strings) rather than silently failing. **HYPOTHESIS**: the marker-provenance classification
(textbook vs literature vs card) lives in the web layer (`web/src/lib/provenance.ts`, asserted by
`tests/test_citation_provenance.py`), i.e. provenance is surfaced at render time; I did not find a
backend field on `QAResult` tagging each citation's origin (origin is inferred from which list it's
in: `citations` vs `literature.citations` vs cards lane).

---

## 12. Existing tests & evaluation code

**FACT.** `tests/` is pytest, mirroring the packages: `tests/neuro_core/`, `tests/rehearsal/`,
`tests/eval/monitor/`, and many `tests/test_*.py`. Directly relevant:
- `tests/test_qa.py` — exercises `answer_question` (Lane A/B orchestration; `lane_a`/`lane_b`
  injection seams exist for this, `qa.py:103`).
- `tests/test_ask_error_handling.py`, `tests/test_ask_submission_isolation.py`,
  `tests/test_ask_claim_confidence.py` — the `/api/ask` route contract & error surface.
- `tests/test_server_spa.py`, `tests/test_serve_phone.py` — server boot / SPA fallback / phone serve.
- `tests/test_retrieve.py`, `tests/test_disambig_eval.py`, `tests/test_citation_provenance.py`.

**Existing eval / live-judge harnesses (parity references for the runner):**
- `eval/textbook/run_eval.py` — calls `neuro_core.query.get_engine()` and drives
  `engine.embedder.embed_query` → `engine.index.hybrid_search` → `engine.reranker.rerank`, with
  optional `engine.synth_fn(...)` to synthesize. **This is a working example of calling the engine
  in-process below the `answer_question` level.**
- `eval/live_text_judge.py`, `eval/live_image_judge.py`, `eval/run_eval.py`, `eval/case_eval.py`,
  `eval/figure_eval.py`, `eval/textbook/disambig_eval.py` — live LLM-judged harnesses; baselines in
  `eval/BASELINE.json`, `eval/LIVE_BASELINE.json`.
- **eval-monitor (Milestone 1, commit 6c486bb):** `eval/monitor/` — detection core
  (`detect.py`, `fingerprint.py`, `baseline.py`, `contracts.py`, `suppress.py`, `digest.py`,
  `detectors/coverage_drop.py`), tested under `tests/eval/monitor/`.
- The new benchmark framework scaffold is `evaluation/` itself (`evaluation/README.md`): 67 questions
  with stable IDs (`NIS-`, `SPINE-`, `TUMOR-`, `GENERAL-`, `OPEN-CV-`, `FUNCTIONAL-`, `TRAUMA-`),
  source inputs in `evaluation/inputs/` (`contemporary-qs-in-neurosurgery`, `nsgy-questioner.txt`,
  `nsgy-grader.txt`), schemas/runs/reports dirs already created.

**HYPOTHESIS:** I did not find an existing "ws6-live-judge" module by that exact name in this
worktree; the live-judge family is `eval/live_text_judge.py` / `eval/live_image_judge.py`. If
"ws6-live-judge" is a process/PR label, its code likely corresponds to those files.

---

## 13. Recommendation for the 67-question runner

**Call the engine in-process — do NOT drive the browser, and prefer in-process over HTTP.**

**Why in-process (FACTS):** (a) `POST /api/ask` adds zero synthesis — it just calls
`answer_question` and serializes (`api/server.py:343`); (b) in-process avoids the
30–180 s-per-question browser-automation flakiness the questioner protocol exists to manage; (c) it
yields the richer native objects (raw `Figure.image_path`, full `Citation` fields) without the
URL-rewrapping the route does; (d) there is precedent — `eval/textbook/run_eval.py` already calls the
engine in-process.

**Exact invocation:**
```python
import os
os.environ.setdefault("SYNTH_PROVIDER", "vertex")         # confirm
# GOOGLE_CLOUD_PROJECT must be inherited (see caveat) — assert it:
assert os.environ.get("GOOGLE_CLOUD_PROJECT"), "Vertex project not set"

from neuro_caseboard.qa import answer_question             # qa.py:103
from neuro_core.query import Clarification                 # query.py:35

res = answer_question(question_text, force=True)           # force bypasses GPU guard; no-op under vertex
```

**Fields to capture per question (record exactly these; never fabricate):**
- `kind`: `"clarification"` if `isinstance(res, Clarification)` else `"answer"`.
- For an answer: `res.answer` (full text — do NOT truncate, per protocol);
  `res.citations` → list of `{n, book, chapter, page}`;
  `res.figures` → list of `{source_n, book, chapter, page, caption, image_path}`;
  `res.literature` → `{narrative, citations:[{n,pmid,title,journal,year,doi,url}]}` or `None`.
- For a clarification: `res.question`, `res.variants` → `[{label, rewrite}]`; pick the most
  comprehensive variant, **record the chosen label**, then re-call
  `answer_question(chosen.rewrite, force=True)`.
- On exception: record `ENGINE ERROR — <Type>: <msg>` and apply the protocol retry ladder.

**Run requirements / how to detect blockers programmatically (FACT):** before the run, assert
`api/server.py:health()` returns `synth == True` **and** `corpus == True` (or call
`_probe_synth()`/`_probe_corpus()` directly). Both are currently **True** on this machine, so a
**real baseline run is possible now**. Set the process env:
`PYTHONPATH=<worktree>:<worktree>/vendor/caseprep`, `python3` interpreter, and ensure
`GOOGLE_CLOUD_PROJECT` + ADC are inherited.

**If byte-identical UI parity is later required:** start `uvicorn api.server:app --host 127.0.0.1
--port 8001` and POST `{"question","force":true}` to `/api/ask`; the JSON shape is defined by
`_citation_dict`/`_figure_dict`/`_literature_dict` (`api/server.py`, L282-329). The answer text is
identical to the in-process path because both call the same `answer_question`.

**Single biggest risk to a clean baseline (HYPOTHESIS, operational):** `GOOGLE_CLOUD_PROJECT` is in
the shell environment but **not** in `.env`; a runner launched without that env inherited will fail
synthesis with an honest 500 / exception. Mitigate by asserting the probe (above) at startup, or by
adding `GOOGLE_CLOUD_PROJECT` to `.env`.
