# Handoff: PubMed retrieval — async dispatch + rate-limit lock fix (2026-07-23)

stopped-at: Nothing pending on this specific change — it's complete and tested. Next
  action for whoever picks this up: decide whether to commit/push it, since this branch
  (`fix/step0-live-bugs`) already has a large pile of pre-existing uncommitted work
  unrelated to this fix (see `branch` below) — don't bundle this in with that pile
  without checking with Michael first.

validated:
  - Root cause: `neuro_caseboard/literature/retriever.py`'s `retrieve()` dispatched 5
    independent PubMed search axes (therapy/systematic_review/etiology/diagnosis/
    prognosis) and 3 independent metadata fetches (summaries/structured_abstracts/
    abstracts) with sequential `await` calls, even though the underlying
    `PubMedClient` (`neuro_caseboard/literature/pubmed_client.py`) is already fully
    async (`httpx.AsyncClient`). 8 sequential round-trips where `asyncio.gather()`
    would let them overlap.
  - Found and fixed a real bug while making this change: `PubMedClient._rate_limit()`
    read `self._last`, `await`ed a sleep, then wrote `self._last` — not atomic. Under
    `asyncio.gather()`, two coroutines could both read the same stale `self._last`
    before either updated it, and fire back-to-back — i.e. naively adding concurrency
    to the old code would have risked violating NCBI's 10 req/s cap (ban risk), not
    just failed to speed anything up. Fixed with an `asyncio.Lock` around the
    read-wait-write in `_rate_limit()`.
  - Changes: `pubmed_client.py` (lock added), `retriever.py` (both dispatch points
    converted to `asyncio.gather`, `import asyncio` added). `gather()` preserves
    input order, so axis priority (used for `rank_of` in the relevance sort) is
    unchanged.
  - Test added: `tests/test_literature_pubmed_client.py::test_rate_limit_serializes_concurrent_dispatch`
    — asserts that 4 `gather()`-ed calls through one `PubMedClient` are still spaced
    by `delay`, not simultaneous. This is the regression test for the exact bug above.
  - Evidence: `uv run pytest tests/test_literature_pubmed_client.py
    tests/test_literature_retriever.py tests/test_case_literature.py -q` → 26 passed,
    0 failed (20 in the first two files including the new test, 6 in case_literature).
  - Not yet measured: actual wall-clock improvement on the live Hetzner deployment.
    This was validated at the unit-test level (rate-limit correctness + no regression
    in existing behavior), not by re-running `LITERATURE_RETRIEVAL=true` against the
    live box. Earlier in this session, the PubMed lane's full contribution was
    measured at ~140-240s (183-380s total vs 140-180s without), but that number
    includes NLI/entailment reprocessing and reranking of added records, not just the
    eutils network calls this fix targets — so don't assume this fix collapses that
    whole gap. Re-run the live A/B before quoting a new number.

branch: `fix/step0-live-bugs` — NOT pushed. This branch already had a large amount of
  pre-existing uncommitted/untracked work before this session touched it (evaluation
  runs, eval scripts, `.run.md`, `FIX_PLAN.md`, `OUTSIDE_REVIEW.md`, an existing
  `SESSION-HANDOFF.md` from 2026-06-29, `uv.lock`, etc. — see `git status`). This
  session's changes are isolated to exactly 3 files:
  `neuro_caseboard/literature/pubmed_client.py`,
  `neuro_caseboard/literature/retriever.py`,
  `tests/test_literature_pubmed_client.py`. Do not `git add -A` or otherwise sweep in
  the rest of that branch's untracked state as part of committing this fix.

in-flight: None. No background jobs running.

do-not:
  - Do not commit/push without Michael's go-ahead (per his standing "PRs stop at the
    manual merge gate" rule in this repo's CLAUDE.md — never self-merge, and given the
    branch's messy pre-existing state, probably wants a clean/isolated commit for just
    this fix).
  - Do not touch or clean up the rest of `fix/step0-live-bugs`'s uncommitted state —
    it's someone else's in-progress work, not part of this task.
  - Do not assume this fix alone explains/fixes the ~240s PubMed-lane latency number
    quoted earlier in the session — that number wasn't re-measured after this change.

## Also discussed this session (not yet acted on)

- **ONNX + INT8 quantization for the reranker**, to re-enable the cross-encoder
  (`bge-reranker-base`) on the Hetzner box, which currently runs
  `CASEBOARD_NLI_MODEL=lexical` because the box only has ~1.8GB RAM free and the
  full-precision cross-encoder OOM-killed the process before (`docker-compose.
  hetzner.yml` line 4 comment confirms this is exactly why lexical was chosen).

  **Why it targets the right constraints:** `bge-reranker-base` is a ~100M-param
  BERT-style encoder. INT8 dynamic quantization on this model class is mature and
  low-risk — `optimum.onnxruntime` (`ORTModelForSequenceClassification`) handles the
  ONNX export, then `onnxruntime.quantization.quantize_dynamic` does the INT8 pass, in
  one straightforward toolchain. Typical results for this model class: ~4x smaller
  weights (fp32 → int8, so roughly 400MB → ~100MB weights) and 2-4x faster CPU
  inference via ONNX Runtime's optimized kernels — which directly attacks both of the
  box's binding constraints (RAM headroom and the 2-vCPU rerank cost that scales with
  `RETRIEVE_K`).

  **Accuracy tradeoff:** reranking only needs correct relative ordering, not exact
  scores, so INT8's small numerical error rarely flips which candidates end up on top
  — expected quality loss is minimal for this use case, though not independently
  benchmarked on this corpus.

  **What it does NOT fix:** rerank cost still scales with `RETRIEVE_K` (keep that low
  regardless), and 2 vCPUs is still a hard ceiling on concurrent-request throughput —
  quantization helps per-request latency/memory, not concurrency.

  **Before flipping the config:** don't assume the quantized model fits the ~1.8GB
  budget from published quantization ratios alone — measure actual RSS with the
  quantized model loaded on the Hetzner box itself before changing
  `CASEBOARD_NLI_MODEL` away from `lexical`, since this exact box already OOM-killed
  the full-precision version once.

  **Status:** discussed only, not started — no ONNX export, no quantization script, no
  RSS measurement, and no docker-compose change has been made yet. Next concrete step
  would be: export + quantize `bge-reranker-base` locally, load it in a throwaway
  process pinned to a memory limit matching the box's ~1.8GB free, and measure RSS +
  per-query latency before touching `docker-compose.hetzner.yml`.
- Deploy config reference: `docker-compose.hetzner.yml` (2 vCPU, ~1.8GB RAM free,
  `RETRIEVE_K`/reranker-model-size are the CPU levers, PubMed fan-out is the literature
  latency lever).
