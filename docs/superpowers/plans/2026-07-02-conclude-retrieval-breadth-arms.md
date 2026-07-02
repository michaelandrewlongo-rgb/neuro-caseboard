# Conclude Retrieval-Breadth Eval Arms — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Grade the already-on-disk retrieval-breadth arms (RERANK_K=20, RETRIEVE_K=80, RRF-only, Qwen3-reranker, Qwen3-embedder) to a machine verdict and retune `RETRIEVE_K`/`RERANK_K` defaults only if a knob decisively wins — all under $3.

**Architecture:** A committed, resumable, budget-gated **paired LLM-judge** (`evaluation/scripts/grade_pairs.py`) reproduces the ad-hoc grader behind `eval/mmr-score-pilot/`. It reads two run.jsonl files (control + arm), presents each question's two answers **blinded and order-randomized** to an independent frontier judge (`anthropic/claude-sonnet-4.5` via OpenRouter — distinct from the `glm-5.2` answer model), collects paired 0–100 scores, and aggregates to `{mean_delta, ci95, t, wins/losses/ties}` matching the existing `mmr-score-summary.json` schema. No answers are regenerated (no synth cost); grading is the only spend.

**Tech Stack:** Python stdlib + `openai` client (OpenRouter base_url), reusing the client/pricing/budget-gate pattern from `evaluation/scripts/judge_verifier.py`.

## Global Constraints

- **Total spend < $3.00.** Judge = `anthropic/claude-sonnet-4.5`; est. ~$1.57 for 104 pairs. Hard per-call budget gate at **$2.50** (leaves headroom for pricing drift). Resume never re-pays.
- **Independent judge:** must NOT be `z-ai/glm-5.2` (the answer model). Sonnet-4.5 is the committed-precedent judge.
- **Blinded + order-randomized** every pair; deterministic seed derived from qid (no `Math.random`/wallclock — must be reproducible/resumable).
- **This is a MACHINE verdict**, explicitly labeled as such in RESULTS.md — it does not override the "A/B grading is human-only" rule; it is the autonomous stand-in the mmr-score-pilot precedent already established. A paid human deploy-synth grade remains the confirmatory step before any default flip is called final.
- **Do not change a default unless an arm is decisively positive** (CI95 excludes 0 AND wins>losses). Score-neutral (CI spans 0) → keep current default, log the null result. Current: `RETRIEVE_K=40`, `RERANK_K=12` (`neuro_core/config.py:22-23`).
- Work on a branch off `master` (not on master directly; not on `feat/nli-verifier-default`).

---

### Task 1: Branch + reproduce the paired judge as a committed script

**Files:**
- Create: `evaluation/scripts/grade_pairs.py`

**Interfaces:**
- Produces CLI: `python evaluation/scripts/grade_pairs.py CONTROL/run.jsonl ARM/run.jsonl OUT_DIR --label "<arm>" [--judge MODEL] [--budget 2.50]`
- Emits `OUT_DIR/<label>-grades.jsonl` (schema `{qid, domain, score_ctrl, score_arm, len_ctrl, len_arm}`) and `OUT_DIR/<label>-summary.json` (schema matching `eval/mmr-score-pilot/mmr-score-summary.json`: `n_paired, mean_ctrl, mean_arm, mean_delta_arm_minus_ctrl, sd, se, ci95, t, wins, losses, ties, judge, total_cost`).

- [ ] **Step 1:** `git checkout master && git checkout -b eval/conclude-retrieval-breadth`
- [ ] **Step 2:** Write `grade_pairs.py`: reuse `_openrouter_client()` + `_price_per_token()` from `judge_verifier.py`; blind+randomize A/B by `hash(qid)` parity; system prompt asks judge to score each answer 0–100 on a neurosurgery-answer rubric and return JSON `{"score_a":N,"score_b":N}`; unblind to ctrl/arm; append-only resume keyed by qid; per-call budget gate identical to `judge()`; aggregate with stdlib `statistics` (paired delta, t = mean/se, ci95 = mean ± 1.96·se).
- [ ] **Step 3:** Self-check: `python evaluation/scripts/grade_pairs.py --selftest` runs the aggregation on 3 synthetic pairs and asserts mean/t/wins are correct (no network, no spend).
- [ ] **Step 4:** Run selftest, confirm PASS.
- [ ] **Step 5:** Commit: `feat(eval): committed paired LLM-judge for A/B answer grading`.

### Task 2: Grade the config-knob arms (highest ROI — can retune defaults)

**Files:** reads `evaluation/runs/control-fixed`, `rerank_k-20-fixed`, `retrieve_k-80-fixed`.

- [ ] **Step 1:** Grade RERANK_K=20 vs control → `evaluation/runs/graded-breadth/rerank_k-20-summary.json`.
- [ ] **Step 2:** Grade RETRIEVE_K=80 vs control → same dir.
- [ ] **Step 3:** Record running spend after each (budget gate enforces <$2.50).

### Task 3: Grade the model-swap arms (won't retune, but concludes the sweep)

- [ ] **Step 1:** Grade RRF-only (`rerank-none`) vs control.
- [ ] **Step 2:** Grade Qwen3-reranker (`rerank-qwen3`) vs control.
- [ ] **Step 3:** Grade Qwen3-embedder (`embed-qwen3`) vs control.

### Task 4: Verdict, default decision, RESULTS.md, memory

**Files:** `neuro_core/config.py:22-23` (only if a knob decisively wins), `evaluation/RESULTS.md`, memory `model-bakeoff-knob-findings.md`.

- [ ] **Step 1:** Read all `*-summary.json`; build the verdict table (arm, Δ, CI95, t, W/L/T, cost).
- [ ] **Step 2:** Apply decision rule. If RETRIEVE_K=80 or RERANK_K=20 has CI95 excluding 0 AND wins>losses → bump the default in `config.py`; else keep 40/12 and log null.
- [ ] **Step 3:** Append a row per arm to `evaluation/RESULTS.md` via prose (label: "machine judge, sonnet-4.5, bakeoff-21").
- [ ] **Step 4:** Update memory `model-bakeoff-knob-findings.md` with the concluded verdict + total spend.
- [ ] **Step 5:** Commit; open PR to master.
