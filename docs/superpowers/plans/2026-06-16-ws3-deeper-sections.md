# Plan — WS-3: Deeper, less-redundant, better-cited sections (test-first)

Spec: `docs/superpowers/specs/2026-06-16-ws3-deeper-sections-design.md`. Strict TDD.

## Tasks

1. **Measure.** Probe the deterministic scaffold's slot coverage per section → Clinical Summary
   drops `key_findings` + `functional_baseline` on a sparse case. (Done.)
2. **RED.** `tests/test_case_facets.py`: deterministic scaffold covers every facet of every section
   for a sparse case (and a rich case). Run → fail (Clinical Summary missing 2 facets).
3. **GREEN.** `case_author.py`: emit `key_findings` + `functional_baseline` unconditionally with a
   generic non-fabricating fallback; sharpen `CASE_SYSTEM` to name the per-section facet checklist.
   Run → green; `test_case_author.py` (no-foreign-literal grep) stays green.
4. **Dedup lock.** `tests/test_dedup.py`: mixed two-near-dup + two-distinct regression → green
   (threshold already calibrated; no `dedup.py` change).
5. **Literature guard.** `tests/test_case_literature.py`: `section_query` stays case-specific →
   green (no focus-token / recency change; `ask` unchanged).
6. **Gate.** `eval/quality_gate.py` `facet_coverage` metric; bump `eval/BASELINE.json`.
7. **Verify.** Full `pytest` green, 0 regressions; gate green; build/ask/cards unchanged.
8. **Record.** LOOP_LOG line.

## Non-goals
The real-anatomy plate (WS-4); intake (WS-5); the live judge (WS-6); retuning the dedup threshold or
literature recency/focus tokens (no offline signal; avoid over-fitting the stochastic judge).
