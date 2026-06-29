# Guidelines Testing Sandbox — Design

**Date:** 2026-06-29
**Status:** Approved (design); implementation plan pending
**Author:** Michael + Claude

## Problem

42 clinical-guideline sources (free society/AHA/ESO/NASS/AO/etc. guidelines) were
appended into the live shared index (`…/neuro-textbook-rag/index`, now 60 sources,
all 42 tagged `GUIDELINES — …`). A surfacing probe shows they actively reshape
retrieval on management questions (guideline in top-5 on 11/12 guideline-sensitive
queries). That is exactly why they must **not** ship to the live product until tested:
they change behavior, and the change has not been proven net-positive.

We want to (a) hold the guidelines as a potential resource, (b) keep the live product
provably unchanged, and (c) test the guidelines — under a deliberately **fast/cheap
model stack** — in an isolated sandbox before any promotion.

## Goals

- Live product is **provably** back to the original 18 textbooks (no guideline rows,
  no guideline PDFs in the live corpus) — safe even against a fresh process or a
  viewer restart.
- A real, separate sandbox that contains all 60 sources and runs a **fast/cheap model
  stack** (DeepSeek V4 Flash synthesis + Vertex Gemini 2.5 Flash disambiguation).
- A repeatable A/B harness that measures whether guidelines help, with a clear
  graduation rule, plus real latency/cost numbers for the cheap stack.

## Non-goals (YAGNI)

- No engine-level retrieval filter (the two index dirs are the A/B arms).
- No sandbox corpus dir / sandbox reindex (sandbox runs off the copied index).
- No new A/B harness — **reuse the existing `evaluation/` harness** (see the
  `neuro-caseboard-ab-test` skill). The only new code is the DeepSeek client.
- No automated promotion/merge — graduation is a manual, gated step.
- Live model config (GLM 5.2 + gemini-3.1-flash-lite) is untouched.
- **Model-quality A/B deferred.** The sandbox bundles two changes (guidelines +
  cheap model stack); a valid A/B changes ONE variable. This test holds the model at
  the cheap stack and varies only the corpus. "Is the cheap stack as good as the live
  GLM stack?" is a separate one-variable A/B, out of scope here.

## Architecture

### 1. Index isolation (no re-embedding)

- **Live** `…/neuro-textbook-rag/index` → revert to **18 textbooks** by deleting rows
  where `book LIKE 'GUIDELINES — %'` from the `chunks` and `figures` tables. Cheap,
  reversible.
- **Sandbox** `…/neuro-textbook-rag/index-sandbox` → a **copy of today's 60-source
  `.lance` tables** (`chunks`, `figures`, `books`, `cards`, `meta`). It shares the
  existing `assets/figures/` directory — `figure_path` values are absolute and read at
  serve time, so no asset duplication and figures resolve unchanged.
- **Ordering / safety:** copy → sandbox **first**, verify it has 60 books, *then*
  delete the guideline rows from live. The sandbox copy is a full backup; if anything
  is wrong, restore by copying back.
- The two index dirs **are** the A/B arms — selected by `TEXTBOOK_INDEX_DIR` (already
  an overridable env var; zero code change to point at either):
  - **WITHOUT guidelines** = live index (18).
  - **WITH guidelines** = sandbox index (60).
  Textbook chunks are bit-identical across arms, so guidelines are the only corpus
  variable.

### 2. Corpus / held guidelines

- Move the 42 `GUIDELINES — *.pdf` out of `…/textbook_pdfs` into `…/guidelines_held/`.
  Live corpus returns to 18 textbook PDFs and stays clean for any future reindex.

### 3. Sandbox model stack (env overrides only; live config unchanged)

Sandbox env lives at `~/.config/neuro-caseboard/sandbox.env` (gitignored, outside the
repo, `chmod 600`), holding `DEEPSEEK_API_KEY` and the sandbox model overrides. Loaded
only by the sandbox harness, never by the live `.env`.

| Role | Live (unchanged) | Sandbox |
|---|---|---|
| Synthesis | `z-ai/glm-5.2` (OpenRouter) | **`deepseek-v4-flash`** (DeepSeek direct API) |
| Disambiguation | `google/gemini-3.1-flash-lite` (OpenRouter) | **`gemini-2.5-flash`** (Vertex) |
| Embed / rerank | local BGE (unchanged) | local BGE (unchanged) |

- **Only new engine code:** a ~10-line `DeepSeekSynthClient` (OpenAI-compatible,
  `base_url=https://api.deepseek.com`), `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` config
  knobs, and a `provider == "deepseek"` branch in `make_synth_client`. Vertex
  disambiguation needs **no** code — `make_analyze_client` already supports a `vertex`
  provider; set `ANALYZE_PROVIDER=vertex`, `ANALYZE_MODEL=gemini-2.5-flash`.

### 4. A/B via the existing `evaluation/` harness (one variable: corpus)

Reuse `evaluation/` per the `neuro-caseboard-ab-test` skill. The A/B changes **only the
corpus**; the model is held fixed at the cheap stack in env for **both** arms, so the
delta is attributable to the guidelines alone.

- **Index dir is the lever** (`INDEX_DIR` / `TEXTBOOK_INDEX_DIR`):
  - **Baseline arm** = live index (18 textbooks).
  - **Treatment arm** = sandbox index (60, with guidelines).
- **Fresh baseline required.** The existing `baseline-20260620-134705` was generated on
  the GLM stack — reusing it would confound model + corpus. Generate a **new
  cheap-stack baseline** (18 textbooks, DeepSeek + Vertex-flash) so both arms share the
  same model.
- **Procedure** (existing scripts): satisfy the harness Hard Gate (change is live +
  reaches the graded textbook-lane answer) → `run_benchmark.py` into immutable run dirs
  for each arm → **attribution check** (count guideline citations in treatment answers;
  expect 0 → many) → blinded paired grading by **Claude subspecialty graders**
  (`make_blinded_pair.py`, rubric `evaluation/inputs/nsgy-grader.txt`; not the answer
  model — avoids self-grading bias) → `summarize_grades.py` / `update_results.py` with
  **drift control** and a **regression / retrieval-crowding scan**. Use the
  progress/early-termination loop to stop once the verdict is decisive.
- **Benchmark = the frozen `benchmark-manifest.jsonl`.** Implementation must first
  **check its coverage of guideline-sensitive management content**; the guidelines help
  on management/evidence questions, so if the frozen 67-Q set under-covers those, the
  test would under-measure the guidelines' value. If so, author a **frozen
  guideline-sensitive question set** as the test target (both arms answer the same
  frozen set — still one variable). This coverage check is the first plan step.
- **Performance read:** the run config records the model stack; capture per-call
  **latency + token usage** (DeepSeek + Vertex-flash) so the report gives the real
  "fast and cheap" numbers alongside the quality verdict.

## Graduation rule

Promote guidelines to live only if, on the held-out set:
- guideline-sensitive question quality **improves** (blind judge), **and**
- textbook-anchored question quality is **non-inferior** (no dilution regression), **and**
- guideline citations are **correct and current** (cited span supports the claim; the
  current edition is cited, e.g. AIS 2026 not 2019).

Failure modes and their fixes:
- Guidelines in-corpus but never retrieved → **inert**; fix retrieval weighting, not content.
- Textbook questions regress → **dilution**; gate guidelines behind query-type routing.

## Data flow

```
question
  → query_analyze (disambiguation)         [sandbox: Vertex gemini-2.5-flash]
  → neuro_core retrieval                    [arm A: live index (18) | arm B: sandbox index (60)]
  → synthesis                               [sandbox: deepseek-v4-flash]
  → answer + citations
  → blinded paired grading                  [Claude subspecialty graders, nsgy-grader.txt]
  → A/B report (quality deltas + drift + regressions + latency/cost)
```

## Testing

- Unit test for the new `DeepSeekSynthClient` (mocked OpenAI client) following the
  existing `synth_clients` test patterns; assert `make_synth_client` routes
  `provider == "deepseek"` to it with the right base URL/model.
- A cheap **retrieval-only smoke check** against both index dirs (no LLM spend) proves
  the two arms load and that guidelines surface in the treatment arm — the harness Hard
  Gate "change is live + reaches the graded answer" before any paid run.
- Existing `eval/run_eval.py` / `quality_gate.py` (or the harness baseline) confirm the
  **reverted live index** still passes its gates — i.e., the revert restored the prior
  18-textbook baseline.

## Reversibility

- Promote later: re-append the held PDFs to the live index (`build_index --new-only`).
- Abandon: delete `index-sandbox` + `guidelines_held`. Live is untouched in both cases.

## Risks / mitigations

- **Deleting guideline rows from live could corrupt the index** → sandbox copy is made
  and verified first as a full backup; LanceDB deletes are versioned.
- **DeepSeek direct key leakage** → stored outside repo, `chmod 600`, never committed;
  rotate if the chat transcript is a concern.
- **A/B confounded by model stack** → both arms use the *same* sandbox model stack, so
  the guideline effect is isolated; comparing the cheap stack to the live GLM stack is
  a separate, out-of-scope question.

## Open items

- All model IDs resolved (`deepseek-v4-flash` confirmed via the DeepSeek API;
  `gemini-2.5-flash` on Vertex approved).
- **Benchmark coverage of guideline-sensitive content** is the first plan step (see §4):
  inspect `benchmark-manifest.jsonl`; if management/evidence questions are under-covered,
  author a frozen guideline-sensitive question set as the test target. Resolved in the
  plan, not a blocker for the design.
