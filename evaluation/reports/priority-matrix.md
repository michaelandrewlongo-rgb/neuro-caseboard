# Priority Matrix

`priority = clinical_severity × frequency × causal_confidence × estimated_fixability`

Each factor scored 1 (low) – 5 (high). **Frequency ≠ importance**: a single safety/reliability defect
that is cheap to fix and removes the only non-answer can outrank a high-count cluster whose fix is a
large, risky overhaul. Severity here reflects *clinical decision impact*, not raw count.

| Cluster | severity | frequency | causal_conf | fixability | **priority** | notes |
|---|---|---|---|---|---|---|
| **C5 disambiguation empty-answer** | 4 | 2 | 5 | 5 | **200** | only not-gradable (SPINE-02); narrow, testable production reliability fix; high confidence |
| **C1 corpus evidence-currency** | 4 | 5 | 5 | 2 | **200** | 60% of defects; caps scores; fix = literature-lane augmentation (larger, network-dependent) |
| **C2 synthesis completeness** | 3 | 4 | 3 | 3 | **108** | missing thresholds/comparators/risks; targeted prompt requirement, testable |
| C3 over-absolute language | 2 | 3 | 3 | 5 | 90 | calibration instruction; low severity, easy |
| C4 incorrect synthesis / mis-scoping | 3 | 2 | 3 | 2 | 36 | question mis-reading; hardest to fix narrowly |

## Selected interventions (budget-aware; favor narrow, testable fixes over broad prompt rewrites)

**Intervention #1 — C5: disambiguation empty-answer reliability fix (TOP).**
Highest priority tie, highest fixability. A disambiguated re-call that yields an empty/None answer must
never surface as a non-answer — fall back to answering the original (broad) question. Narrow, high causal
confidence, directly testable (reproduce SPINE-02 → assert non-empty answer), low regression risk. **Selected.**

**Intervention #2 (budget permitting) — C3: calibrated-uncertainty / over-absolute language.**
A narrow, low-risk prompt-calibration change with a measurable target (the 38 over-absolute defects) and an
easy regression test (sentinel strong answers must not degrade). Preferred over C1/C2 for a second pass
because C1 (corpus augmentation) is a large network-dependent change that risks latency/comparability for the
post-improvement run, and C2 risks becoming a broad prompt rewrite. **Candidate — confirm in root-cause.**

**Deferred (documented, not attempted this pass):**
- **C1 corpus evidence-currency** is the highest-*impact* cluster but its remediation (enabling/strengthening
  the PubMed literature lane to inject 2022–2025 evidence) is a substantial, network-dependent change with
  real regression and latency risk for a 67-question rerun. It is recorded as the top *deferred* item with a
  concrete remediation surface (`neuro_caseboard/literature/`), to be tackled as its own focused effort rather
  than rushed within this loop's budget. Attempting it carelessly would risk the "no unexplained regression"
  success criterion.
- C2 and C4 remain open tickets.

This selection honors the spec: a supported root cause, a measurable expected outcome, a regression test, and
a rollback path are required before any change — C5 meets all four; C1 is explicitly deferred rather than
half-implemented.
