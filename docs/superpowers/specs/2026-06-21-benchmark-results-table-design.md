# 67-Q Benchmark Results Table — Design

**Date:** 2026-06-21
**Status:** Approved (brainstorm), pending implementation plan
**Scope:** A persistent, human-readable table of every full 67-question benchmark run, plus a script that updates it.

## Problem

Every full run of the frozen 67-question neurosurgery benchmark produces a score, but there is
**no central, persistent record** that lets you see, at a glance, the baseline and how each
subsequent run did and *what change* distinguishes it. Today:

- Single-arm runs emit a canonical `<prefix>-summary.json` (mean 0–100, grade distribution,
  unsafe count, by-domain) via `summarize_grades.py`.
- A/B runs emit only `ab-comparison.csv` + `unblind_grades.py` **stdout** (no summary JSON).
- "What change was made" lives only in the run-dir name and `run-config.json`
  (`application_commit`). The prose `evaluation/experiment-ledger.md` tracks *interventions*, not
  runs, and is hand-written. The `neuro-caseboard-ab-test` skill says "write a SUMMARY" but fixes
  no location — so the last A/B (youmans) run never got one.

## Goals

- A single **human-readable** markdown table, `evaluation/RESULTS.md`, with the **baseline run as
  the first row** and **one row per subsequent scored run** (one row per **arm** for A/B runs),
  each distinguished by a plain-language **Change** label.
- The table **explains itself**: a short preamble states what it is, how to read it (baseline is
  the reference; Δ is the change vs baseline; **Unsafe must stay 0**), and how it is updated.
- A script, `evaluation/scripts/update_results.py`, that **upserts** a row from a run's existing
  outputs so the table is updated after every full run without hand-editing.
- Seed the table with the three existing runs so it is immediately useful.
- Wire the update step into the `neuro-caseboard-ab-test` skill and the reproduce block so it is
  not forgotten.

## Non-goals

- Re-running or re-grading any benchmark (the script only *reads* existing run outputs).
- Replacing `experiment-ledger.md` (interventions) or per-run `*-summary.json` (canonical metrics).
- Changing the grading pipeline, the manifest, or `summarize_grades.py`/`unblind_grades.py` output
  schemas. (A/B rows use whatever fields the A/B outputs already contain.)
- Charts, web rendering, or a database. Markdown only.

## The table: `evaluation/RESULTS.md`

A self-describing preamble (plain language) followed by one markdown table.

**Preamble (verbatim intent):**

> # 67-Question Benchmark — Run Results
>
> One row per full run of the frozen 67-question neurosurgery benchmark. The **baseline** row is
> the reference point; every other row shows what changed and how the score moved.
>
> **How to read it:** **Mean** is the average answer score from 0–100 (higher is better). **Δ vs
> base** is this run's mean minus the baseline's — positive means better than baseline. **Unsafe**
> is the count of answers a grader flagged as unsafe; this must stay **0**. **A/B/C/D** is how many
> answers earned each letter grade. Small mean differences (±2–3) are usually run-to-run noise, not
> a real change.
>
> **How it's updated:** after a full run, `evaluation/scripts/update_results.py` adds or refreshes
> that run's row from its score files (see the command at the bottom). Do not hand-edit rows.

**Columns:**

| Run | Date | Change | Commit | n | Mean | Δ vs base | A/B/C/D | Unsafe | Notes |
|-----|------|--------|--------|---|------|-----------|---------|--------|-------|

- **Run** — the run id / directory name (e.g. `baseline-20260620-134705`), plus arm for A/B
  (`youmans-full67-… · youmans_pubmed`).
- **Date** — run creation date (from `run-config.json` `created_at`, else parsed from the dir name).
- **Change** — plain-language label of what distinguishes this run (`baseline` for the anchor row;
  e.g. `C5 empty-answer guard`, `woven-on`, `woven-off`). Supplied via `--label`.
- **Commit** — short `application_commit` from `run-config.json`, with a `dirty` marker if the
  working tree was dirty.
- **n** — number of graded questions.
- **Mean** — overall mean score (0–100), one decimal.
- **Δ vs base** — `mean − baseline_mean`, signed, one decimal; `—` for the baseline row and if no
  baseline row exists yet.
- **A/B/C/D** — grade-distribution counts as `a/b/c/d` (omitting F/not-gradable into Notes if
  present); `—` when the run's outputs carry no letter grades (some A/B outputs).
- **Unsafe** — unsafe-answer count; `—` when not present in the run's outputs.
- **Notes** — free text: keep/revert decision, caveats (e.g. length confound), not-gradable count.

A trailing fenced code block shows the exact `update_results.py` invocation, so a reader knows how
rows get added.

## The updater: `evaluation/scripts/update_results.py`

A small, pure-where-possible CLI. Reads existing run outputs (never the engine/LLM/network),
computes a row, and **upserts** it into `evaluation/RESULTS.md` keyed by `(Run, arm)` — re-running
updates the row in place rather than duplicating it. Recomputes **Δ vs base** for the written row
from the current baseline row's mean. Creates `RESULTS.md` (preamble + header) if absent. Always
keeps the baseline row first.

**Two input modes:**

1. **Single-arm** (`--summary <…-summary.json> --run <run-id> --label "<change>"
   [--commit <sha>] [--date <iso>] [--baseline] [--note "<text>"] [--decision keep|revert]`):
   reads `overall_score.{n,mean}`, `grade_distribution`, `unsafe_answer_count` from the canonical
   summary JSON. `--baseline` marks/pins the row as the baseline anchor. `--commit`/`--date`
   default from the run's `run-config.json` when discoverable.

2. **A/B** (`--ab <run-dir> --label "<change>" [--note] [--decision]`): discovers arms from
   `grading/keymap.json`; for each arm computes mean and (if present) grade dist / unsafe from
   `ab-out/<arm>-grades.jsonl`; emits **one row per arm** keyed `(run-id, arm)`, with Change =
   `<change> (<arm>)`. Cells the A/B outputs don't provide render as `—`.

**Upsert mechanics:** parse the markdown table out of `RESULTS.md`, build a dict keyed by
`(Run, arm)` from existing rows, replace-or-insert the computed row(s), re-render the table
(baseline row first, then the rest in insertion order), write back the file (preamble untouched).

**Determinism:** no `Date.now()`-style nondeterminism in the row content — `Date` comes from the
run's metadata or `--date`. Idempotent for the same inputs.

## Seeding

On first implementation, populate three rows from existing runs (this also exercises both modes):

- `baseline-20260620-134705` → `--baseline`, label `baseline`, mean 77.74.
- `post-improvement-20260620-182930` → label `C5 empty-answer guard`, mean 79.36.
- `youmans-full67-20260620-2210` → A/B mode, one row per arm (`recent`, `youmans`,
  `youmans_pubmed`).

## Wiring (so the table isn't forgotten)

- `neuro-caseboard-ab-test` skill, step 7: add an explicit instruction to run `update_results.py`
  (single-arm or A/B form) with a `--label` describing the change, after grading.
- `NEURO_CASEBOARD_EVALUATION.md` reproduce block: append the `update_results.py` call as the final
  step of a full run.

## Testing (TDD; hermetic + scoped per CLAUDE.md)

Pure file-IO tests under `tests/evaluation/` using `tmp_path`:

- **Single-arm row:** a fake `*-summary.json` → a row with the expected mean / grades / unsafe.
- **Baseline + Δ:** writing baseline then a second run yields the correct signed Δ; baseline row Δ
  is `—`.
- **Upsert idempotency:** writing the same run id twice yields one row (updated), not two.
- **Baseline pinned first:** adding a non-baseline run before/after the baseline keeps baseline as
  row 1.
- **A/B expansion:** a fake run-dir with `keymap.json` + two `ab-out/<arm>-grades.jsonl` → two arm
  rows with means from the grades; missing letter-grade/unsafe fields render `—`.
- **Missing file:** running against a non-existent `RESULTS.md` creates it with the preamble +
  header + the row.
- **Preamble preserved:** a second upsert does not duplicate or mangle the preamble.

## Risks

- **A/B output schema variance** (do `ab-out/<arm>-grades.jsonl` carry letter grades / unsafe
  flags?) → the plan inspects the real youmans files; columns the data lacks render `—` rather than
  guessing.
- **Markdown table parsing fragility** → restrict parsing to the single fenced table region under a
  known header; treat anything else as opaque preamble/footer and pass through untouched; tests
  cover round-trip.
- **Drift between this table and the canonical JSON** → the table is a *view*; the script always
  recomputes from the source files, never edits numbers by hand.
