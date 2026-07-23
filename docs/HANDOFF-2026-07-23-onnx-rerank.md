# Handoff: INT8/ONNX reranker — implemented, deployed, measured (2026-07-23)

stopped-at: The ONNX reranker is live on the Hetzner box and verified. Two things are
  waiting on Michael: (1) OpenRouter credits are EXHAUSTED, so every `/api/ask` returns
  500 — this is unrelated to the reranker change but means the app is currently
  answer-less; (2) the branch `fix/pubmed-async-dispatch` has 2 commits and is pushed
  but NOT merged (no PR opened, per the repo's manual-merge rule).

## What shipped

`RERANK_MODEL` pointing at a **directory** now loads an INT8/ONNX cross-encoder through
onnxruntime; a bare hub id still loads the torch `CrossEncoder`. One `os.path.isdir`
branch in `neuro_core/rerank.py`, plus:

- `neuro_core/onnx_rerank.py` — `OnnxCrossEncoder.predict(pairs)`, the only surface
  `rerank.py` and `NLIVerifier` use. Uses the Rust `tokenizers` lib, **not**
  `transformers.AutoTokenizer`, which imports torch (+1.0GB RSS, measured) and would
  defeat the purpose.
- `neuro_core/scripts/quantize_cross_encoder.py` — produces the model directory.
- `tests/neuro_core/test_onnx_rerank.py` — 9 tests, fake session/tokenizer (no model in CI).
- `pyproject.toml` — `onnx` extra (runtime: onnxruntime/tokenizers/numpy, torch-free) and
  `onnx-export` extra (build-time: optimum/torch). `Dockerfile` installs `[...,onnx]`.

## Measured (do not re-quote without re-measuring)

Model, `BAAI/bge-reranker-base`: weights **1112MB → 279MB**.

Standalone scorer, this WSL2 box, 320 real corpus pairs vs the fp32 torch CrossEncoder:

| | fp32 torch | INT8 ONNX |
|---|---|---|
| peak RSS | 1675 MB | 889 MB |
| load | 17.0 s | 3.1 s |
| score 320 pairs | 136.1 s | 40.7 s |

Ranking agreement (the thing that actually matters for rerank): **0.91 mean top-8
overlap, Kendall tau 0.878, 7/8 queries top-1 identical**. So roughly one passage in
eight differs at the margin. INT8 is close, but it is NOT free — the handoff that
proposed this assumed "minimal" quality loss; that assumption is now measured, not assumed.

On the Hetzner box, the full retrieval lane (`plan_retrieval`: embed + search + figures +
rerank) over 3 questions: **fp32 64.3s → ONNX 50.5s total (21% faster, ~4.6s/query)**.

## The finding that changes the plan

**Quantizing the reranker does NOT free the RAM needed to re-enable the NLI gate.**

The original plan was: shrink the reranker → win back RAM → flip `CASEBOARD_NLI_MODEL`
off `lexical`. Measured on the box, that premise does not hold. With the ONNX reranker
live (torch-free itself), a single `plan_retrieval` call still shows
`torch_resident=True` and **peak RSS 3314 MB** on a 3.8GB box — because the *embedder*
(`BAAI/bge-large-en-v1.5`) is a torch/sentence-transformers model that loads regardless.
The reranker was never the only torch consumer, so removing it from torch does not remove
torch. Adding a ~1-2GB NLI cross-encoder on top of a 3.3GB peak would still OOM.

If re-enabling NLI is the goal, the next lever is the **embedder**, not the reranker:
quantize `bge-large-en-v1.5` the same way (the same `OnnxCrossEncoder`-style path would
need an embedding equivalent), or move to a smaller embedding model. Do not flip
`CASEBOARD_NLI_MODEL` before that, and re-measure RSS on the box when you do.

## Box state (Hetzner `hub`, /opt/caseboard)

- Running image built from `fix/pubmed-async-dispatch` (CD dispatch `v0-onnx-rerank`),
  healthy. `RERANK_MODEL=/models/bge-reranker-base-onnx-int8`.
- Quantized model at `/opt/caseboard/models/bge-reranker-base-onnx-int8` (283MB),
  mounted read-only at `/models`.
- `docker-compose.yml` was edited on the box: added `container_name: caseboard`, the env
  the old hand-run container carried but the file lacked (`LITERATURE_RETRIEVAL`,
  `RETRIEVE_K`, `RERANK_K`, `RERANK_MODEL`, `VISUAL_RETRIEVAL`, `HF_HUB_OFFLINE`,
  `TRANSFORMERS_OFFLINE`), the hf-cache mount, and the `/models` mount. Backups:
  `docker-compose.yml.bak-20260723` (pre-compose-adoption) and `.bak-preonnx`.
- **Rollback is config-level, no image needed:** set `RERANK_MODEL: BAAI/bge-reranker-base`
  in the compose file and `docker compose up -d`. The fp32 weights are still in
  `/opt/caseboard/hf-cache`, and the running image supports both paths.
- `docker compose` was not installed on the box (Docker 29 without the plugin);
  installed `docker-compose-v2`. The old container was a hand-run `docker run`, now
  compose-managed.

## Disk (was an incident)

The box hit **100% disk, 0 bytes free** — two 11GB caseboard images. Michael approved
deleting the superseded untagged image; after the ONNX pull the previous one was pruned
too. Now **76% used, 8.8GB free**. Each build is ~11GB, so **two images fit and three do
not** — prune after every cutover or this recurs. The 11GB image size is itself worth
attacking (torch dominates it); the `onnx` extra is a step toward a torch-free image but
the embedder still requires torch today.

## Blocked / needs Michael

- **OpenRouter credits exhausted.** `/api/ask` returns 500; the traceback is
  `openai.APIStatusError: 402 ... requires more credits`. End-to-end latency could NOT be
  re-measured for this reason. Either top up credits, or switch the box to the documented
  free alternate (`SYNTH_PROVIDER=vertex`, `VERTEX_MODEL=gemini-2.5-pro` — ADC is already
  mounted). I did not switch it: that changes which model writes answers he grades blind.
- **Branch not merged.** `fix/pubmed-async-dispatch` = the PubMed async commit + this one.
  No PR opened.

## Not done

- No A/B of answer quality with the ONNX reranker (blocked by the credits issue above).
  The 0.91/0.878 ranking agreement is the only quality evidence so far; a real check is
  the 67-question benchmark via the `neuro-caseboard-ab-test` skill once synthesis works.
- The `onnx` extra is installed in the image but nothing else uses it yet (the NLI
  verifier could take an `OnnxCrossEncoder` — `predict` already returns raw multi-class
  logits for that case, and the tests cover it — but no quantized NLI model was built).
