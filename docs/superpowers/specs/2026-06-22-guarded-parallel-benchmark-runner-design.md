# Guarded parallel benchmark runner — design

**Date:** 2026-06-22
**Status:** approved
**Goal:** Cut wall-clock of future 67-Q A/B runs ~2× via bounded parallelism, with memory guards
that make a run *likely to succeed* on this 16 GB WSL2 box — without ever risking the swap-death
that the sequential one-id-per-call pattern was chosen to avoid.

## Why (measured, not assumed)

- Per-worker peak RSS = **5.07 GB** (`VmHWM`, plateaued; a *lower bound* on the max — heavy
  questions peak higher). Box = 16 GB RAM + 4 GB swap, 24 cores. CPU is never the bottleneck
  (~0.6 core/worker); **memory is**.
- Safe concurrency inequality: `N × peak + OS baseline (~2 GB) < 16 GB`, swap untouched.
  N=2 → ~12 GB (safe); **N=3 → ~17 GB → forces swap → thrash** (the wedge we prevent). So N is
  capped at 2.
- Records in `run.jsonl` are **93–142 KB** (≫ 4 KB `PIPE_BUF`), so two processes appending to one
  file would interleave and corrupt. Each worker therefore needs its **own** `run.jsonl`.

## Component

One new script `evaluation/scripts/run_benchmark_parallel.py` that **wraps** the existing
`run_benchmark.py` (the runner is unchanged). Three responsibilities:

### 1. Preflight memory gate (`choose_n`)
Pure arithmetic over available RAM:
```
PEAK_GB    = 5.5   # 5.07 observed + margin for heavier questions   ← calibration knob
CUSHION_GB = 2.0   # buff/cache reclaim lag + transient spikes        ← calibration knob
N_MAX      = 2     # research finding: N=3 spills to swap
raw = floor((available_gb - CUSHION_GB) / PEAK_GB)
N   = min(raw, N_MAX)          # 0 (or negative) ⇒ abort
```
- Idle (~14 GB free) → N=2; busy (~9 GB) → N=1; `< 7.5 GB` free → **abort** + print top-RSS
  processes so the user knows what to close (report-only; never kills).
- Available RAM via `psutil` (lazy import) → falls back to `/proc/meminfo:MemAvailable` if psutil
  absent, so the gate still works headless.

### 2. Concurrency-safe split
IDs are split **round-robin** across N shards; each shard gets its own dir `$RUN/shard-<i>` and is
driven by the *same* one-id-per-call `--resume` loop as today (one sequential writer per shard).
Workers are short-lived (one question → process exit) so the memory ceiling stays flat at
`N × peak`, never accumulating.

### 3. Merge
After all shards finish, merge `$RUN/shard-*/run.jsonl` → `$RUN/run.jsonl` (dedup by
`question_id`, tolerate a partial last line), copy `run-config.json`. Downstream
(`finalize_run.py`, grading, `summarize_grades.py`, aggregation) runs **unchanged** — it never
knows the run was sharded.

## Error handling
- Gate degrades (2→1) or aborts with guidance (chosen behavior: *degrade then abort*).
- A crashed shard leaves its partial `run.jsonl`; re-running with `--resume` picks up where it
  stopped. Merge is idempotent (rebuilt from shards each call).

## Testing (one check on the money path)
`tests/evaluation/test_run_benchmark_parallel.py` over the **pure** functions only:
`choose_n` (ample / tight / abort boundaries), `round_robin_split`, `merge_records` (dedup,
partial-line tolerance). No Vertex, no subprocess, no psutil (functions take values as args).

## Integration
Update `.claude/skills/neuro-caseboard-ab-test/SKILL.md` §Procedure step 3 to call the
orchestrator instead of the raw loop, documenting the gate + degrade + "what to close" report.

## Explicitly out of scope (YAGNI)
Process-killing (report-only, user's call); fp16/quantization or a shared model-server (over-eng
for an occasional run); a config file for the two constants (knobs live in the script with their
calibration comment).
