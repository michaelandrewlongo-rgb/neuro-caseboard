# TKT-C4 — Question mis-scoping / over-narrow decomposition

- **Failure-mode ID / category:** C4 / `incorrect_synthesis` + `poor_question_decomposition` + `disambiguation_failure` (the deeper, secondary defect behind SPINE-02)
- **Severity / priority:** material / **P3** (priority 36; 20 `incorrect_synthesis` defects + the SPINE-02 narrowing)
- **Labels:** `severity:material` `subsystem:query` `stage:query-understanding` `status:open`
- **Affected questions:** TUMOR-08 (reads "laser" as percutaneous disc decompression, not LITT), TUMOR-01 (misframes supramarginal resection), TUMOR-04 (leaves LITT unanswered), SPINE-02/SPINE-03 (compound "A and/or B" question narrowed to one limb).
- **Artifact links:** `evaluation/reports/root-causes/C5-disambiguation-empty-answer.md` §5 (secondary defect), `failure-analysis.md` (C4).

## Observed vs expected
- **Observed:** the engine misreads question scope or splits a deliberately compound question (e.g. "cervical **or** lumbar") into mutually exclusive variants, then answers only one limb.
- **Expected:** a compound multi-region/multi-modality question is answered in full (decomposition), not narrowed via either/or disambiguation.

## Suspected layer & causal confidence
query_understanding / query_decomposition. The LLM `analyze` pass (`neuro_core/query_analyze.py:146-155`, `ANALYZE_SYSTEM_PROMPT`) treats a compound "A and/or B" question as single-axis variant ambiguity. **Causal confidence: high** for the SPINE-02 narrowing (directly observed); medium for the broader mis-scoping.

## Status — OPEN (deferred)
Fix candidates: (a) tighten `ANALYZE_SYSTEM_PROMPT`/`_parse_analysis` so coordinated "A and/or B" questions return `ambiguous=False`; or (b) guard `Engine._plan_query` to answer the full compound question. Deferred this pass: it is a deeper query-understanding change, riskier than the C5 reliability guard, and the C5 guard already removes the *non-answer* symptom (worst case becomes a complete answer to half the question rather than a blank).

## Acceptance criteria
Compound coordinated questions answered in full without spurious disambiguation; no regression on genuinely ambiguous single-axis questions that *should* disambiguate.
