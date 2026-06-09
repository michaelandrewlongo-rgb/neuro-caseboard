# Local quantized synthesis backend — design

**Date:** 2026-06-09
**Branch:** `local-quantized-synthesis` (off `master`)
**Status:** approved (brainstorming)

## Goal

Let the RAG answer pipeline run synthesis on a **local quantized LLM** served on the
user's own GPU, with **zero cloud spend** and no passages/figures leaving the machine —
selectable via `SYNTH_PROVIDER=local`, alongside the existing `vertex` and `openrouter`
providers. Success = a real question answered end-to-end through the local model with
correct citations, and a correct refusal on an out-of-corpus question.

## Context / what already exists

The provider abstraction (`engine/synth_clients.py::make_synth_client`) already switches
on `SYNTH_PROVIDER`. A near-complete implementation of the `local` provider exists
**uncommitted** in a sibling worktree (`neuro-textbook-rag-local-synth`, branch
`local-synth-fallback`). We are **porting that proven code** onto this branch in the main
checkout — not rewriting it. The ported pieces:

- `LocalSynthClient(OpenRouterSynthClient)` — reuses the OpenAI-compatible request path,
  overrides only `base_url` (Ollama at `http://localhost:11434/v1`) and a dummy api-key.
- `make_synth_client` routes `synth_provider == "local"` → `LocalSynthClient`.
- Config keys `LOCAL_BASE_URL`, `LOCAL_MODEL` (+ defaults), `.env.example` docs.
- Unit tests for provider selection and config defaults.

## Design

- **Runtime:** Ollama (OpenAI-compatible `/v1`; manages GGUF; WSL2 GPU passthrough).
  Installed as a setup step; not a Python dependency.
- **Retrieval stays on the GPU (default `EMBED_DEVICE=auto`→cuda).** A query's workload is
  retrieval **and** synthesis together; we don't move the embed/rerank/visual lanes off the
  GPU. This project simply expects to be the *only* GPU user while it runs.
- **Per-query GPU readiness guard (new — the heart of this requirement).** Before each query
  executes, a guard (`engine/gpu_guard.py`) inspects the GPU via `nvidia-smi` and enforces:
  (a) **clear of other projects** — no *foreign* compute process holds VRAM (ComfyUI,
  VibeVoice, a stray python, etc.); VRAM held by our own Ollama process counts as ours, not
  foreign, so a warm model never false-trips it; and (b) **can handle the workload** —
  effective free VRAM ≥ a configurable budget (`GPU_MIN_FREE_MIB`, default sized to
  retrieval + the chosen LLM). On failure the query **aborts with a clear, actionable
  message** naming the process(es) using the GPU and the VRAM shortfall, instead of OOM-ing
  or silently offloading to CPU. A `--force` flag (warn-and-proceed) is the only override.
  `cli/ask.py` (and the server query path) call the guard at entry.
- **Model:** `qwen2.5:7b-instruct` (Q4_K_M, ~5 GB). Rationale: the query holds the retrieval
  stack (~4 GB) **and** the LLM on the same **12 GB** card, so a 7B keeps the whole workload
  resident with headroom; a 14B (~9 GB) + retrieval would overflow. `num_ctx` is set to 8192
  via a custom Modelfile so the ~6 passages aren't silently truncated (a grounding risk).
  `LOCAL_MODEL` / `num_ctx` stay configurable; a larger model is opt-in only if it still
  loads 100% on GPU (`ollama ps`) alongside retrieval.
- **Text-only fidelity (adjustment to ported code):** the user chose text-only, so
  `LocalSynthClient.generate` is **overridden to omit figure images** (a text model on
  Ollama may error or silently drop image content). Figure *source entries and captions*
  remain in the prompt text (`synthesize.py::_format_appended`), so citations and figure
  display are unaffected — the model simply does not describe figure pixels. The
  corresponding test is updated to assert images are **not** sent for the local client.

## Out of scope

- Vision / figure-image description by the local model (text-only by decision).
- Quality-parity eval gating vs the Gemini baseline (`eval/run_eval.py`) — a follow-up,
  not a blocker for "running."
- Any frontend / server-API change. `SYNTH_PROVIDER` already flows through.

## Verification (validate before integration)

1. `pytest` for `tests/test_synth_clients.py`, `tests/test_config.py`, and a new
   `tests/test_gpu_guard.py` (faked `nvidia-smi` output) pass.
2. Ollama installed; model pulled; a custom Modelfile sets `num_ctx=8192`. Server reachable
   at the configured base URL.
3. **GPU guard works (hard gate):** with the GPU clear, the guard passes and the query runs
   with the model **100% on GPU** (`ollama ps`); with a foreign workload occupying VRAM (or
   free VRAM below `GPU_MIN_FREE_MIB`), the guard **trips** per the chosen behavior, naming
   the offending process — it does not proceed into OOM/offload.
4. `cli/ask.py` with `SYNTH_PROVIDER=local`:
   - an in-corpus question → grounded answer carrying bracketed `[n]` citations, at an
     acceptable token rate;
   - an out-of-corpus question → the verbatim refusal string.
5. Full `pytest` suite still green.

## Risks / mitigations

- **Another project squatting on the GPU mid-query** → the per-query guard aborts early with
  a message naming the process, so you free it and re-run rather than OOM.
- **Our own warm Ollama model misread as "busy"** → the guard treats VRAM held by our Ollama
  process as available, so a loaded model doesn't false-trip the guard.
- **VRAM co-residency (retrieval + LLM)** → default to 7B (~5 GB) so the combined ~10 GB
  workload fits the 12 GB card; larger models opt-in only if `ollama ps` stays 100% GPU.
- **Context truncation silently degrading grounding** → Modelfile `num_ctx` ≥ measured prompt
  size (target 8192); verify a real query isn't truncated.
- **WSL2 GPU passthrough / Ollama not on PATH** → verify `nvidia-smi` sees the model under
  Ollama and a trivial `/v1/chat/completions` smoke call before wiring the CLI.
