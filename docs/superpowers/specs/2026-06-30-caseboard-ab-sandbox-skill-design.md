# Caseboard A/B Sandbox skill — Design (short spec)

**Date:** 2026-06-30
**Status:** Built (`~/.claude/skills/caseboard-ab-sandbox/`)
**Origin:** generalized from the guidelines A/B run (see `eval/sandbox/SUMMARY-guidelines-ab.md`).

## Problem

The guidelines A/B was a one-off on this branch. We want it reusable: a skill, usable on any
branch or master, that produces **completely blinded A/B output the user grades themselves**,
then unblinds to a verdict.

## Decisions (user-approved)

- **User-level skill** (`~/.claude/skills/caseboard-ab-sandbox/`) so it works on every branch /
  worktree / master. It **carries its own** blinding/scoring scripts (those weren't on master)
  and **drives the repo's** `evaluation/scripts/run_benchmark.py` + frozen 67-Q manifest (which
  are on master).
- **Arms = env-override sets** (e.g. `INDEX_DIR` for corpus A/B, `SYNTH_PROVIDER`+model for model
  A/B) run on the current checkout, plus a **branch recipe** (run one arm per checked-out branch).
  No auto-checkout of the shared working dir (avoids the streaming-answers collision class).
- **Self-graded, blinded**: deliver `PAIRS.md` (every Q, Answer A/B, order randomized per
  question, no arm labels) + `scoresheet.csv` (blank `score_A,score_B,better,notes`) + a hidden
  `.keymap.json`. User fills the sheet; `score.py` unblinds → verdict. Human-only (the
  Claude-graded path stays in the separate `neuro-caseboard-ab-test` skill).

## Components

- `SKILL.md` — procedure, the one-variable rule, hard gate, branch recipe, regression-scan guidance.
- `scripts/run_arm.sh` — run one arm: source its env → `run_benchmark.py` → `finalize_run.py`.
- `scripts/make_blinded.py` — two run dirs → `PAIRS.md` + `scoresheet.csv` + hidden `.keymap.json`
  (A/B order = sha256(question_id) → deterministic, balanced; stdlib only).
- `scripts/score.py` — filled `scoresheet.csv` + `.keymap.json` (+ run dirs for latency) → per-arm
  means, paired delta + rough `paired_t` (|t|>2 ≈ p<0.05), head-to-head, regression scan,
  `verdict.json` + `comparison.csv` (stdlib only).

## Validation

End-to-end against the real guidelines run dirs: rebuilt the blinded pack, auto-filled the
scoresheet from the known per-question scores via the new keymap, and `score.py` reproduced the
committed verdict exactly (baseline 84.07 / guidelines 85.30, delta +1.22, t 1.33 n.s.,
head-to-head 36/21/10, 21 regressions). Blinding checked: no arm label leaks into answer text.

## Non-goals

LLM auto-grading (separate skill), auto-checkout of branches, a sandbox reindex, promotion logic.
