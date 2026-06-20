# TKT-C2 — Synthesis omits requested decision thresholds / comparators / risks / patient-selection

- **Failure-mode ID / category:** C2 / `missing_decision_threshold` + `missing_comparator` + `missing_risk_or_tradeoff` + `missing_patient_selection`
- **Severity / priority:** material→minor / **P2** (priority 108; 102/406 defects)
- **Labels:** `severity:material` `subsystem:prompting` `subsystem:synthesis` `stage:answer` `status:open`
- **Affected questions:** broad — most C/D answers omit at least one requested decision element.
- **Artifact links:** `evaluation/reports/root-causes/C2-synthesis-completeness.md`, `failure-analysis.md` (C2).

## Observed vs expected
- **Observed:** answers omit a numeric decision threshold, a named comparator, a risk/trade-off, or patient-selection criteria the question explicitly requests.
- **Expected:** decision-grade answers enumerate thresholds, comparators, risks, and selection criteria where asked.

## Suspected layer & causal confidence
prompting / model_synthesis (the synthesis prompt may not require structured decision coverage), partly downstream of C1 (missing evidence → missing comparator). **Causal confidence: medium.**

## Status — OPEN (candidate intervention #2, confirm scope)
A narrow prompt requirement to enumerate decision thresholds/comparators/risks is plausible and testable, but risks drifting into a broad prompt rewrite (which the spec cautions against) and overlaps C1. Held as a candidate; intervention #2 will prefer the lower-risk C3 calibration change unless C2 can be scoped narrowly with a clean regression test.

## Acceptance criteria
Targeted lift on completeness defects on affected questions, no regression on sentinel strong answers, no latency/safety regression. Requires a prompt-level change with a measurable before/after on the affected subset.
