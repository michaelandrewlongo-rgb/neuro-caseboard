# Design — WS-3: Deeper, less-redundant, better-cited section content

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §4 WS-3); implementation complete
- **Branch:** `worktree-loop+output-quality`
- **Loop:** Output-Quality (`caseboard case`), Pass 3 of 6

## 1. Context & problem

The blind text judge measures section *coverage of `must_cover`* + overall — but that lever is
LLM-graded and **deferred** (no provider in CI). The durable, offline-verifiable levers WS-3 can pin
in CI are: (a) the **deterministic scaffold covers every section's facet** (so depth doesn't depend
on rich input), (b) **dedup** keeps depth from becoming repetition, and (c) the literature query
stays **case-specific** (relevance starts with an on-topic query). Measuring the deterministic
scaffold found a real gap: Clinical Summary dropped `key_findings` + `functional_baseline` whenever
the case lacked imaging / functional-status data.

## 2. Decisions

- **The facet checklist is the section's own slot vocabulary** (`CASE_SECTIONS[*].slots`) — a
  documented topic-agnostic carve-out, never a clinical answer. The deterministic scaffold must
  enumerate every facet of every section, even for a sparse case, with a generic (non-fabricating)
  prompt when the specific datum is absent.
- **`CASE_SYSTEM` makes the checklist explicit** — "cover every section, and within it every listed
  facet" — aligning the LLM author with the same per-slot completeness (graded live in WS-6).
- **Dedup is already well-calibrated** (Jaccard 0.72); WS-3 adds a mixed regression test (two
  near-identical + two distinct claims) rather than retuning the threshold and risking the existing
  collapse/keep tests.
- **Literature stays case-specific; defaults unchanged for `ask`.** `section_query` already embeds
  `case.to_topic()`; WS-3 adds a regression guard rather than retuning focus tokens / recency (no
  offline signal to optimize against, and the brief forbids over-fitting the stochastic judge).
- **The facet invariant is gated** — a new `facet_coverage` metric (fraction of eval cases whose
  deterministic scaffold covers every facet of every section) folds into `quality_gate.py` +
  BASELINE, so a future facet regression fails CI.

## 3. Detailed design

- `case_author.py`: emit `key_findings` + `functional_baseline` unconditionally (generic fallback
  prompt when imaging / functional_status absent); sharpen the `CASE_SYSTEM` completeness rule to
  name the per-section facet list as the checklist.
- `eval/quality_gate.py`: `facet_coverage` metric (deterministic-scaffold slot coverage per eval
  case); `eval/BASELINE.json` bumped (1.0).
- Tests: `tests/test_case_facets.py` (sparse + rich case facet coverage), `tests/test_dedup.py`
  (mixed near-dup + distinct regression), `tests/test_case_literature.py` (query case-specificity).

## 4. Acceptance criteria (LOOP_PROMPT §4)

- The deterministic scaffold covers every section's facet checklist (unit test counts facets per
  section); the build/ask paths are untouched.
- A dedup regression test proves distinct facts survive while near-duplicates collapse.
- `[L#]` on the reasoning sections remain non-fabricated; `ask` literature output unchanged.
- 0 regressions.

## 5. Testing strategy (TDD)

`test_case_facets.py` RED (sparse case missing 2 facets) → GREEN (unconditional facets). Dedup +
literature guards added green (the behaviors already hold; the tests lock them). `facet_coverage`
folded into the gate.

## 6. EVAL

- Offline: `quality_gate.py` `facet_coverage` 1.0 (gated); dedup + literature non-fabrication green.
- Live (WS-6, deferred): text-judge mean `must_cover` coverage 80.7% → ≥ 85%, overall 8.2 → ≥ 8.6,
  red-flag contamination 0 — the LLM author's facet checklist + dedup feed this.

## 7. Risks

- **Over-fitting the live judge.** Mitigation: durable, topic-agnostic, slot-driven changes only;
  no clinical literals (guarded by the existing no-foreign-literal grep test); literature focus
  tokens / recency defaults left unchanged.
- **Build/ask drift.** `CASE_SYSTEM` + the scaffold are case-path only; the full suite (468) +
  goldens confirm `build`/`ask`/`cards` are unchanged.

## 8. Out of scope

The real-anatomy plate (WS-4); intake accuracy (WS-5); the live judge run (WS-6).
