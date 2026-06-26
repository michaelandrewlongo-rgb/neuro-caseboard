# Bake-off 21-Q Knob-Sweep Runbook

Spec: `docs/superpowers/specs/2026-06-26-ask-knob-sweep-design.md`. One variable per arm; report `$`.

## 0. Frozen env block (paste into every fresh shell, then override ONE var)

```bash
cd /home/michael/PROJECTS/neuro-caseboard
export PYTHONPATH="$PWD:$PWD/vendor/caseprep"
export SYNTH_PROVIDER=openrouter   OPENROUTER_MODEL=z-ai/glm-5.2
export ANALYZE_PROVIDER=openrouter ANALYZE_MODEL=google/gemini-3.1-flash-lite
export RETRIEVE_K=40 RERANK_K=12
export EMBED_MODEL=BAAI/bge-large-en-v1.5  RERANK_MODEL=BAAI/bge-reranker-v2-m3
export LITERATURE_WEAVE=true LITERATURE_K=12
export LITERATURE_CACHE_DIR="$PWD/eval/pubmed-snapshot" LITERATURE_CACHE_TTL_DAYS=36500
export MAX_FIGURE_IMAGES=0
export INDEX_DIR=/home/michael/neuro-textbook-rag/index CORPUS_DIR=/home/michael/textbook_pdfs
printenv SYNTH_PROVIDER OPENROUTER_MODEL RERANK_K   # sanity: openrouter / z-ai/glm-5.2 / 12
```

## 1. Preflight (once)

```bash
# contamination audit — expect exit 0 / "nothing deletable"
python3 -m neuro_core.scripts.purge_contamination --index-dir "$INDEX_DIR"; echo "exit=$?"
# index fingerprint — anchor the index state
python3 evaluation/scripts/index_fingerprint.py "$INDEX_DIR" | tee eval/index-fingerprint.json
# freeze PubMed (fetch + cheap rewrite; ~$0.02 total) — populates eval/pubmed-snapshot/
python3 evaluation/scripts/warm_pubmed.py evaluation/inputs/bakeoff-21.manifest.jsonl
```

## 2. Control run (the baseline leg)

```bash
RUN=evaluation/runs/control-$(date +%Y%m%d-%H%M%S)
python3 evaluation/scripts/run_benchmark.py --run-dir "$RUN" \
    --manifest evaluation/inputs/bakeoff-21.manifest.jsonl --timeout 300
python3 evaluation/scripts/finalize_run.py --run-dir "$RUN"
# Liveness: spot-check answers resemble the bake-off glm-5.2 quality (~86 easy / ~90 hard).
CONTROL="$RUN"; echo "CONTROL=$CONTROL"   # save this path; every arm diffs against it
```

## 3. Env-only arms (zero code) — one var over the frozen block

```bash
# Output breadth: RERANK_K 12 -> 20
ARM=evaluation/runs/rerank_k-20-$(date +%Y%m%d-%H%M%S)
RERANK_K=20 python3 evaluation/scripts/run_benchmark.py --run-dir "$ARM" \
    --manifest evaluation/inputs/bakeoff-21.manifest.jsonl --timeout 300
python3 evaluation/scripts/finalize_run.py --run-dir "$ARM"
python3 evaluation/scripts/make_pair.py "$CONTROL/run.jsonl" "$ARM/run.jsonl" "RERANK_K=20" "$ARM/baseline-vs-rerank_k-20.md"

# Candidate breadth: RETRIEVE_K 40 -> 80
ARM=evaluation/runs/retrieve_k-80-$(date +%Y%m%d-%H%M%S)
RETRIEVE_K=80 python3 evaluation/scripts/run_benchmark.py --run-dir "$ARM" \
    --manifest evaluation/inputs/bakeoff-21.manifest.jsonl --timeout 300
python3 evaluation/scripts/finalize_run.py --run-dir "$ARM"
python3 evaluation/scripts/make_pair.py "$CONTROL/run.jsonl" "$ARM/run.jsonl" "RETRIEVE_K=80" "$ARM/baseline-vs-retrieve_k-80.md"
```

## 4. Make the grading sheet (per arm)

`$CONTROL` from §2 and `$ARM` from §3 (the §3 block above now runs these automatically — this section shows the manual/standalone form).

```bash
python3 evaluation/scripts/make_pair.py \
    "$CONTROL/run.jsonl" "$ARM/run.jsonl" "RERANK_K=20" "$ARM/baseline-vs-rerank_k-20.md"
```

## 5. Cost

Per arm ≈ 21 × $0.02 ≈ **$0.42** (glm-5.2 $0.95/$3.00 per M). Read actual tokens from each
answer's `raw_response`; report `$` after every arm.

## Code-change arms (separate just-in-time plans)

- Reranker (RRF-only off-switch; Qwen3-0.6B scorer), PubMed rewrite (toggle `rewrite_pubmed_query`),
  embedder (Qwen3 re-index + query-prefix fix), fusion (`index.py` RRF k/weights), figures
  (`MAX_FIGURE_IMAGES>0`). Each gets its own plan when reached; see the spec §6 phases A/D/E/F.
