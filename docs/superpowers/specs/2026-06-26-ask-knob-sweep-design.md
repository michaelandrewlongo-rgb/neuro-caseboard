# Ask-Quality Retrieval-Knob Sweep — Design Spec

- **Date:** 2026-06-26
- **Status:** Approved (design). Implementation plan pending.
- **Branch:** `eval/ask-knob-sweep` (off `master`, post PR #78/#80/#81).
- **Roles:** Michael Longo grades the answer pairs; Claude generates the runs.

---

## 1. Goal & non-goals

**Goal.** For each retrieval-side knob in the **Ask** pathway, produce a
**harness-matched answer-set pair** — `baseline` vs `exactly one knob changed` — on a
fixed 21-question set, so the user can grade baseline-vs-new by eye and decide keep/revert.
The deliverable is **answer artifacts with airtight single-variable provenance**, not scores.

**Non-goals (explicitly out of scope):**

- **Grading, scoring, noise statistics.** The user grades. No LLM graders, no paired
  bootstrap, no minimum-detectable-effect / noise-floor measurement. (The originally
  proposed "Phase 2: anchor + 3× noise floor" is **cut** at the user's instruction.)
- **Synthesis & disambiguation models.** Settled in PR #80 — synth `z-ai/glm-5.2`;
  disambiguation `google/gemini-3.1-flash-lite`, which the bake-off found has **no
  measurable effect on answer quality** (chosen for ~7× speed). Frozen, not tested.
- **Woven on/off.** Settled in PR #78 (`LITERATURE_WEAVE=true` default). Frozen on.
- **Broad parameter sweeps.** Only the specified one-step changes. Expand a range
  (e.g. `RERANK_K=30`, `RETRIEVE_K=60/100`) **only** if failure analysis of the one-step
  result motivates it.

---

## 2. Comparison methodology — single variable, you grade

There is no noise-floor averaging, so the entire validity of the eyeball comparison rests on
**experimental control**: each pair differs by *exactly one* knob, with everything else
byte-frozen.

- **The control run.** One baseline run at the frozen default config (1×, ungraded),
  produced by the **same harness** as the arms. Every arm is diffed against this one control.
  It must come from the same harness — diffing against the bake-off PDFs would reintroduce
  "different tool" as a hidden second variable. The control should reproduce the bake-off's
  glm-5.2 quality (≈86 easy / ≈90 hard human means) as a free liveness check.
- **Each arm = control config + one knob changed.** Same 21 questions, same frozen index,
  same frozen PubMed cache, same model, figures off (until the figures arm).
- **Output = a side-by-side answer pair** per arm for the user to grade.

---

## 3. Eval set — the bake-off 21 questions

| Set | n | Source | Notes |
|---|---|---|---|
| Easy (board-style) | 10 | `~/Downloads/neuro-caseboard-ask-glm-5.2_2026-06-26.pdf` | **off-benchmark**; near-ceiling |
| Hard (benchmark) | 10 | committed manifest | qids below |
| Hard (custom) | 1 | `~/Downloads/neuro-caseboard-ask-HARD-glm-5.2_2026-06-26.pdf` | `CUSTOM-11`, ruptured R-M2 aneurysm operative technique |

Hard benchmark qids: `NIS-02, OPEN-CV-04, OPEN-CV-07, TUMOR-01, TUMOR-05, SPINE-01,
SPINE-06, FUNCTIONAL-02, TRAUMA-02, GENERAL-01`.

**Report results split easy/hard.** The hard 11 are the retrieval-sensitive probe; the easy 10
are near-ceiling and exist mainly to mirror the bake-off and catch regressions.

---

## 4. Frozen config (the control; = bake-off = repo defaults)

Every arm exports this **frozen env block** verbatim, then overrides **exactly one** variable.
Nothing is left to inherited env (the live shell carries a stale `SYNTH_PROVIDER=vertex`) or to
silent config defaults.

```bash
export PYTHONPATH="$PWD:$PWD/vendor/caseprep"
# --- model (settled; frozen) ---
export SYNTH_PROVIDER=openrouter   OPENROUTER_MODEL=z-ai/glm-5.2
export ANALYZE_PROVIDER=openrouter ANALYZE_MODEL=google/gemini-3.1-flash-lite
# --- retrieval (the knobs; frozen at defaults in the control) ---
export RETRIEVE_K=40 RERANK_K=12
export EMBED_MODEL=BAAI/bge-large-en-v1.5  RERANK_MODEL=BAAI/bge-reranker-v2-m3
# --- literature / woven (frozen) ---
export LITERATURE_WEAVE=true LITERATURE_K=12
export LITERATURE_CACHE_DIR="$PWD/eval/pubmed-snapshot" LITERATURE_CACHE_TTL_DAYS=36500
# --- figures off until the figures arm ---
export MAX_FIGURE_IMAGES=0
# --- data paths ---
export INDEX_DIR=/home/michael/neuro-textbook-rag/index CORPUS_DIR=/home/michael/textbook_pdfs
# OPENROUTER_API_KEY + NCBI_API_KEY auto-load from repo .env
```

The whole Ask path is OpenRouter + PubMed — **no Vertex / ADC needed** for the sweep.

---

## 5. Validity controls (the load-bearing part)

1. **Harness honesty.** `evaluation/scripts/run_benchmark.py:170-171` *hard-overrides*
   `SYNTH_PROVIDER=vertex VERTEX_MODEL=gemini-2.5-pro`. Patch it to **honor the env** so glm-5.2
   actually runs. Without this every run is silently Vertex Gemini.
2. **Explicit frozen env block** (§4) on every arm — single-variable guarantee.
3. **Index fingerprint.** Record row counts + `id`-sha256 for `chunks`/`figures`/`cards` before
   the sweep; re-check after the embedder re-index. The embedder arm builds into a **separate
   `INDEX_DIR`**, leaving the control index untouched.
4. **PubMed freeze.** Warm `LITERATURE_CACHE_DIR` once over the 21 questions, `TTL=36500`, so
   woven literature is identical across the textbook-knob arms (the woven answer *includes*
   literature — confirmed: `qa.answer_question` → `_answer_question_woven` when
   `LITERATURE_WEAVE` is on, which is default-true).
5. **Vascular-sort invariant.** `query.py:227` (the off-domain stable sort) stays in **every**
   reranker arm, including RRF-only — else that arm silently changes two things.
6. **Knob stamping.** `run-config.json` captures only the 4 model knobs, **not** retrieval knobs.
   Stamp the knob value in the run-dir name **and** a `NOTES.md`, or the arms are
   indistinguishable after the fact.

---

## 6. Phases

### Phase 0 — make the harness honest + runnable on 21 Qs  *(code, ~no API cost)*

- Patch `run_benchmark.py` to honor `SYNTH_PROVIDER` (drop the vertex hard-override).
- Add a `--manifest <path>` flag (or `MANIFEST_PATH` env) to `run_benchmark.py` so a **standalone
  21-Q manifest** can be run **without polluting** the frozen 67-Q
  `evaluation/inputs/benchmark-manifest.jsonl`.
- Build `eval/bakeoff-21.manifest.jsonl`: the 10 hard qids (copy from the committed manifest) +
  10 easy + 1 custom (extract verbatim question text from the two bake-off glm-5.2 PDFs).
- Runner: **serial** `run_benchmark.py` by default (21 Qs ≈ 16 min/run). Optional: cherry-pick the
  N≤2 memory-gated `run_benchmark_parallel.py` from `feat/guarded-parallel-benchmark` only if
  wall-time bites.

### Phase 1 — index integrity + freeze  *(preflight, one-time)*

- **Contamination audit** (read-only): `python -m neuro_core.scripts.purge_contamination
  --index-dir $INDEX_DIR`. Expect clean / exit 0 (purge already applied 2026-06-23).
- **Fingerprint + provenance**: record commit SHA, corpus file list, and per-table row count +
  `id`-sha256 for `chunks`/`figures`/`cards` (small LanceDB snippet → `eval/index-fingerprint.json`).
- **Arm the PubMed freeze**: warm `eval/pubmed-snapshot/` once over the 21 questions via a
  **literature-only pass** (call `qa.retrieve_records` directly, **no synthesis → zero glm cost**),
  set `TTL=36500`. Warming lit-only *before* the control run guarantees the control and every
  textbook arm hit byte-identical frozen records.

### Control run  *(baseline leg; 1×, ungraded)*

Frozen env block (§4), 21 Qs → `evaluation/runs/control-<ts>/`. Sanity-check the answers resemble
the bake-off glm-5.2 outputs (liveness).

### Phase A — Reranker  *(code)*

Arms vs control (`bge-reranker-v2-m3` = control):
- **RRF-only / no reranker** — add an off-switch (e.g. `RERANK_MODEL=none` sentinel) that
  bypasses the unconditional rerank call (`query.py:226`) and slices RRF-fused hits directly.
  **Keep `query.py:227`** (vascular sort).
- **Qwen3-Reranker-0.6B** — requires a **custom scorer** (it is a causal-LM reranker, not a
  `sentence_transformers.CrossEncoder`; the current loader at `rerank.py:13` won't load it).
  Gate this arm behind the RRF-only-vs-bge result: only build it if the reranker proves to be a
  meaningful lever.

### Phase B — Output breadth `RERANK_K`  *(env-only)*

`RERANK_K=20` vs control's `12`. Test `RERANK_K=30` **only if 20 improves** (per user: the project
already expanded 6→12 under an eval gate; `8` is not retested).

### Phase C — Candidate breadth `RETRIEVE_K`  *(env-only)*

`RETRIEVE_K=80` vs control's `40`. **No** 20/40/60/100 sweep unless a recall failure surfaces in
the 80 result.

### Phase D — PubMed rewrite / query formulation  *(config/code; HIGH priority)*

User flags literature composition as the largest observed quality lever; runs after the cheap
textbook-breadth knobs but ahead of the expensive embedder/fusion arms.

- **Prerequisite (discovery):** locate the query-formulation / rewrite mechanism in
  `neuro_caseboard/literature/retriever.py` + `qa.py` and its toggle. (The cache key is
  `build_query_terms(question)|k|recency_years|recency_boost` — the LLM rewrite's exact role
  relative to the cache must be confirmed before designing the arm.)
- **Single-variable design:** warm a **second** PubMed cache for the alternative formulation **at
  the same wall-clock moment** as the frozen control cache, so records don't drift in time; then
  control (default formulation) vs arm (rewritten formulation) differ only in the query.
- This is the one phase that intentionally **unfreezes** literature.

### Phase E — Embedder  *(full re-index + code; GATED)*

`EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B` vs control's `bge-large-en-v1.5`.
- Full **parallel re-index** into a separate `INDEX_DIR` (`python -m neuro_core.scripts.build_index`).
- Code: make the query-side instruction prefix (`embed.py:5`, hardcoded BGE phrasing) model-aware;
  Qwen3-Embedding expects a different instruction format.
- **Gate:** only run if the cheaper env-only knobs (B, C) plateau — a full re-index is the most
  expensive arm (compute + time, though ~no incremental API cost beyond the 21 answers).

### Phase F — Fusion, then figures  *(code; last)*

- **Fusion:** `index.py:22-29` RRF is hardcoded `k=60`, equal dense/sparse weight. Arm = vary `k`
  and/or add a dense-vs-sparse weight; one change at a time.
- **Figures:** flip `MAX_FIGURE_IMAGES>0` and exercise the figure-lane knobs
  (`VISUAL_RETRIEVE_K`, `CAPTION_RETRIEVE_K`). This is the only arm where figures are on.

---

## 7. Per-arm protocol

```text
1. Fresh shell. Export the §4 frozen env block, then override ONE variable (the knob).
2. RUN=evaluation/runs/<knob>-<value>-<ts>; run the 21-Q manifest through run_benchmark.py.
3. finalize_run.py on the run dir.
4. Write NOTES.md stamping: knob, value, control run-dir, index fingerprint, commit SHA.
5. Emit baseline-vs-<knob>.md (control answer | arm answer, per question, easy/hard split).
6. Report the OpenRouter $ for the arm.
```

One variable per arm. Everything else = the frozen control.

---

## 8. Cost model

- glm-5.2 (OpenRouter): **$0.95/M in, $3.00/M out**; observed **≈$0.02/answer** (woven, figures off).
- Per 21-Q arm ≈ **$0.42**. Disambiguation (gemini-3.1-flash-lite) is negligible.
- Full sweep (control + ~8–12 arms) ≈ **$4–6 OpenRouter**, plus re-index compute (Phase E, no API).
- **Cost reported per arm**, as incurred.

---

## 9. Deliverables

- `eval/bakeoff-21.manifest.jsonl` — the frozen 21-Q eval set.
- `eval/index-fingerprint.json` — preflight index state.
- `eval/pubmed-snapshot/` — frozen literature cache.
- `evaluation/runs/control-<ts>/` and `evaluation/runs/<knob>-<ts>/` — answer sets + NOTES.
- `baseline-vs-<knob>.md` per arm — the side-by-side the user grades.
- A short running `eval/SWEEP-LOG.md` — one line per arm (knob, value, cost, user verdict).

---

## 10. Open gates / risks

- **Phase D discovery** must precede its run (locate the rewrite toggle + cache interaction).
- **Phase A Qwen3 reranker** and **Phase E Qwen3 embedder** are gated behind cheaper results;
  both are real code lifts and may be skipped if earlier knobs settle the question.
- **No noise floor** means a single missed freeze invalidates an arm — §5 controls are mandatory,
  not optional.
- **`RERANK_K`/`RETRIEVE_K`/`RERANK_MODEL`/`EMBED_MODEL` are not in `run-config.json`** — knob
  stamping (§5.6) is the only provenance for retrieval arms.
