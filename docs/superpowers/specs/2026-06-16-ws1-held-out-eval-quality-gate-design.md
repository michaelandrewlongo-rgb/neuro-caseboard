# Design — WS-1: Held-out eval set + automated quality-regression gate

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §2 WS-1); implementation in progress
- **Branch:** `worktree-loop+output-quality`
- **Loop:** Output-Quality (`caseboard case`), Pass 1 of 6

## 1. Context & problem

The Case Dossier engine ships `caseboard case "<dictation>"` → an 8-section print-grade dossier,
but its quality bar is **six hand-graded cases that are also the tuning set**. "Better" is a vibe:
prompts can be tuned against the same cases they're judged on, and there is no automated gate that
fails a build when content/figure quality regresses. Every later workstream in this loop (WS-2…WS-6)
claims to *raise* a measured signal — but there is nothing to measure against.

WS-1 builds that measurement scaffold:
1. A **held-out eval set** — expand `eval/cases.json` + `eval/case_dictations.json` from 6 to ≥24
   cases across ≥7 subspecialties, each tagged `tune` (iteration may see) or `eval` (held out).
2. A deterministic, **offline** `eval/quality_gate.py` that aggregates the offline-computable
   quality signals on the **eval** split and fails (exit 1) if any metric drops below a committed
   `eval/BASELINE.json`, wired into required CI.

This is the bar the rest of the loop is graded on, so it must be honest, offline, deterministic,
and topic-agnostic.

## 2. Decisions

- **`split` is formalized as `tune` | `eval`.** The current values (`dev` → `tune`, `holdout` →
  `eval`) are renamed; nothing in code reads `split` today (verified by grep), so the rename is
  safe. `eval` is held-out: read only by the gate and the nightly judges, never while editing
  prompts. Target partition ≈ 1/3 `tune` ÷ 2/3 `eval`, **disjoint by `id`**.
- **≥24 cases, ≥7 subspecialties.** Target 4–5 per subspecialty across: Spine, Skull base / CPA,
  Vascular – open, Vascular – endovascular, Functional / awake, Neuro-oncology, Pediatric /
  posterior fossa. Each case keeps the existing `must_cover` / `red_flags` schema; each dictation
  keeps the `ground_truth` schema (laterality, level, location, pathology, procedure,
  surgical_goal, comorbidities).
- **The gate reuses the production engine, not a fork** (LOOP_PROMPT §1.6). `quality_gate.py` calls
  the same functions the harnesses and the product call — `parse_dictation` / `deterministic_parse`
  (intake), `build_case_dossier` with the **shared canned PubMed lane imported from `case_eval`**
  (`[L#]`), `deterministic_figure_specs` / `guard_spec` / `filter_specs` / `render_spec` (figures),
  `dedup` (near-dup) — and aggregates their signals. No parallel scoring engine, no new retrieval
  lane.
- **The gate scores only offline, deterministic signals.** LLM-graded coverage/overall stays in
  WS-6 (keyed, never required). The eight gate metrics (see §3.2) are lexical/structural and
  judge-independent — this is the **hard CI bar**.
- **`BASELINE.json` records reality and is the anti-regression floor.** It is committed with the
  *measured* values on the `eval` split at WS-1, and only raised later with a one-line `LOOP_LOG`
  note when a pass intentionally improves a metric. A value below baseline (for `min` metrics) or
  above baseline (for `max` metrics) fails CI.
- **Per-metric direction.** Each baseline metric carries a `direction`: `min` (value must be ≥
  baseline — higher is better: coverages, accuracies) or `max` (value must be ≤ baseline — lower is
  better: near-dup rate, red-flag contamination). This makes "any metric regresses → fail" precise.
- **`corpus_n_coverage` is wired now, measured at its true current value (~0).** WS-2 is what makes
  case operative/technique/structures sections carry `[n]`; today they earn almost none (the
  `_collect_figures` build-only filter bug). The gate includes the metric — computed via an injected
  fake corpus retriever — so the hook exists and WS-2 simply raises its baseline. At WS-1 its
  baseline is whatever is measured (expected 0.0).

## 3. Detailed design (exact files / functions)

### 3.1 Data: `eval/cases.json`, `eval/case_dictations.json`, `eval/figure_spec_cases.json`

- Expand `cases.json` to ≥24 entries; rename existing `split` values; add new entries with
  `subspecialty`, `case_query`, `must_cover` (8–9 facets), `red_flags` (3–4 cross-subspecialty
  distractors), `split`.
- Expand `case_dictations.json` to mirror **every** case `id` with a 4–6 sentence `dictation` +
  `ground_truth`.
- Extend `figure_spec_cases.json` with a few more archetype-grounding cases (cranial corridor,
  spine level, vessel config) drawn from the eval split.

### 3.2 `eval/quality_gate.py` (new)

Pure, importable functions + a `main()`:

```python
def load_split(split="eval") -> EvalData            # cases+dictations+figure cases filtered by split
def compute_metrics(data: EvalData) -> dict[str,float]
def load_baseline(path) -> dict[str, dict]          # {metric: {"value":x,"direction":"min|max"}}
def compare(metrics, baseline) -> tuple[bool, list[Row]]
def main(argv=None) -> int                          # prints table, writes report, exit 0/1
```

Metrics (computed on the **eval** split only, all offline/deterministic):

| metric | source logic | dir |
|---|---|---|
| `section_coverage_det` | `case_eval` 8/8 on deterministic-parse context | min |
| `section_coverage_gt` | `case_eval` 8/8 on ground-truth context | min |
| `intake_side_acc` | `intake_eval` deterministic laterality == gt | min |
| `intake_level_acc` | `intake_eval` deterministic level == gt | min |
| `intake_goal_acc` | `intake_eval` full-parse goal captured | min |
| `lit_coverage` | `[L#]` on Reasoning/Alternatives/Risks via canned lane, no fabrication | min |
| `corpus_n_coverage` | `[n]` on corpus-eligible case sections via injected fake retriever | min |
| `figure_archetype_acc` | `figure_spec_eval` archetype matches | min |
| `figure_side_acc` | side encoded | min |
| `figure_byte_stable` | same spec → identical PNG | min |
| `figure_guard_reject` | side-flipped spec rejected | min |
| `near_dup_rate` | residual cross-section near-dup pairs / case (post-build) | max |
| `red_flag_contamination` | count of `red_flags` phrases appearing in dossier text | max |

`compare` fails if any `min` metric < baseline.value or any `max` metric > baseline.value (with a
tiny epsilon for float equality). `main` prints a per-metric table (metric, value, baseline, dir,
PASS/FAIL), writes `eval/QUALITY_GATE_REPORT_<date>.md`, returns 0 (all pass) or 1.

### 3.3 `eval/BASELINE.json` (new)

`{ "<metric>": {"value": <float>, "direction": "min"|"max"}, ... }` — committed with the WS-1
measured values on the eval split.

### 3.4 `tests/test_quality_gate.py` (new)

Offline pytest (no keys/network). See §5.

### 3.5 CI wiring — `.github/workflows/ci.yml`

Add one step to the `test` job (after the pytest step), on the 3.12 matrix leg only (deterministic,
no need to double-run): `python eval/quality_gate.py`. The gate is offline/deterministic and needs
only core deps already installed by `.[dev]`. `compileall` already covers `eval/` syntax on 3.10.

## 4. Acceptance criteria (from LOOP_PROMPT §2)

- `eval/cases.json` has ≥24 cases, balanced across ≥7 subspecialties, each tagged `tune`|`eval`;
  partition ≈ 1/3 ÷ 2/3 and disjoint by `id`.
- `python3 eval/quality_gate.py` exits 0 on the eval split and prints a per-metric table; exits 1
  if any metric is below `BASELINE.json`.
- The gate runs in required CI and is offline/deterministic (no keys/network).
- 0 regressions; `ask` / `build` / `cards` untouched.

## 5. Testing strategy (TDD)

Write `tests/test_quality_gate.py` FIRST (watch fail), then author data + implement gate:

1. `test_eval_set_size_and_breadth` — ≥24 cases, ≥7 distinct subspecialties, every case has
   non-empty `must_cover` + `red_flags`, `split ∈ {tune,eval}`.
2. `test_split_partition` — tune/eval disjoint by id; eval ≈ 2/3 (between 0.55 and 0.75).
3. `test_dictations_mirror_cases` — every case id has exactly one dictation with the full
   `ground_truth` field set.
4. `test_gate_passes_on_committed_baseline` — `compute_metrics` vs committed `BASELINE.json` →
   `compare` ok is True; `main()` returns 0.
5. `test_gate_fails_when_metric_below_baseline` — synthesize a baseline (tmp) with one `min` metric
   set impossibly high → `compare` ok False; `main(["--baseline", tmp])` returns 1.
6. `test_gate_deterministic` — `compute_metrics` run twice gives byte-identical dict (offline,
   no randomness).
7. `test_gate_reads_only_eval_split` — `load_split("eval")` returns only eval ids; none from tune.

## 6. EVAL

- **Offline:** `quality_gate.py` green on the eval split; baseline committed. Baselines recorded in
  LOOP_LOG: section coverage 8/8 on N/N, intake side/level (measured), figure byte-stable + guard
  N/N, near-dup rate (measured), red-flag contamination 0.
- **Live:** none — this *is* the measurement scaffold (no judge call in WS-1).

## 7. Risks

- **Authoring accuracy.** 21 new clinical cases must be correct and topic-diverse, not over-fit to
  the deterministic engine. Mitigation: facets are standard operative checklist items; red_flags are
  genuine cross-subspecialty distractors; intake baseline records *actual* parser accuracy (WS-5
  raises the hard ones) rather than forcing every dictation to parse cleanly.
- **Gate brittleness.** A too-tight baseline fails on noise. Mitigation: metrics are deterministic
  (no randomness, offline), float compare uses an epsilon, and baselines are set to measured values.
- **3.10 compatibility.** `compileall eval` runs on 3.10. Mitigation: no 3.11+-only syntax in
  `quality_gate.py`.

## 8. Out of scope (this pass)

- LLM-graded coverage/overall (WS-6, keyed).
- Actually *raising* `corpus_n_coverage` (WS-2), section depth (WS-3), the real-anatomy plate
  (WS-4), or intake accuracy (WS-5) — WS-1 only measures the status quo and locks the floor.
- Any safety/governance signal — the red-flag check is a *content-accuracy* (non-contamination)
  signal, not a safety gate (LOOP_PROMPT §Guardrails).
