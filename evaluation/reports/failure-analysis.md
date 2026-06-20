# Baseline Failure Analysis

Source: `evaluation/runs/baseline-20260620-134705/baseline-grades.jsonl` (67 answers, mean 77.74,
median 81, 0 A / 38 B / 22 C / 6 D / 0 F / 1 not-gradable, **0 unsafe**).
Atomic defects: `evaluation/failure-ledger.jsonl` — **406 records**, built deterministically from the
graders' typed criticism arrays (`build_failure_ledger.py`). Severity split: 232 material, 174 minor,
**0 safety-critical**.

## Category distribution (406 defects)

| category | count | dominant severity |
|---|---|---|
| retrieval_omission | 175 | material/minor split |
| outdated_evidence | 70 | material |
| overabsolute_language | 38 | minor |
| missing_comparator | 34 | material/minor |
| missing_decision_threshold | 33 | material |
| missing_risk_or_tradeoff | 24 | material/minor |
| incorrect_synthesis | 20 | material |
| missing_patient_selection | 11 | material |
| disambiguation_failure | 1 | material |

## Clusters (ranked — see priority-matrix.md for scoring)

### C1 — Corpus evidence-currency gap  *(retrieval_omission + outdated_evidence = 245 defects, 60%)*
**Symptom:** Answers are clinically *safe* but omit or mis-date the practice-changing trials and
modalities the questions explicitly name. Independently identified by all 7 subspecialty graders.
Concrete, grader-verified instances (✔ = verified against a real current source via PubMed):
- NIS-01 (D): omits **ESCAPE-MeVO** ✔ and DISTAL (both neutral/with harm signal for distal MeVO);
  repeats an outdated "distal still benefits" claim — the one finding that could mislead toward over-treatment.
- NIS-05: calls the MMA-embolization RCTs "in progress" though **EMBOLISE/STEM/MAGIC-MT** ✔ reported (NEJM 2024).
- NIS-02: treats large-core/basilar thrombectomy as unproven (misses SELECT2/ANGEL-ASPECT/TENSION, ATTENTION/BAOCHE).
- GENERAL-01: reports **ENRICH** as "results pending" — it published positive (NEJM 2024).
- GENERAL-05 / FUNCTIONAL-01: omit **MRgFUS** entirely despite being the named DBS comparator (FDA ET 2016 / PD 2018).
- FUNCTIONAL-04: presents directional/sensing/adaptive DBS as "future" tech (FDA-cleared 2017–2025).
- TRAUMA-06 (D, "not reliable"): omits FDA-cleared plasma **GFAP/UCH-L1** ✔ (ALERT-TBI); conflates decision rules with "AI".
- TRAUMA-02/01/03: miss RESCUEicp ✔ / BEST-TRIP / BOOST-II; uses outdated ICP>20 (vs current >22) threshold.
- SPINE-01 (C): leans on 1990s fusion-favoring data, omits SLIP/SSSS/NORDSTEN-DS.
- TUMOR-05 (C): outdated number-of-lesions cap for brain-mets SRS (contradicts JLGK0901-era practice).

**Probable layer:** retrieval / corpus source coverage. The corpus is a static textbook RAG index
that predates these sources; retrieval cannot surface evidence the corpus does not contain. The repo
*does* have a literature (PubMed) lane (`neuro_caseboard/literature/`, per repository-audit.md) — a
candidate remediation surface. **Causal confidence: high** (post-corpus publication dates are objective;
multiple anchors PubMed-verified). **Fixability: medium** (literature-lane augmentation is plausible but
a larger, network-dependent change).

### C2 — Synthesis completeness gaps  *(missing_decision_threshold 33 + missing_comparator 34 + missing_risk_or_tradeoff 24 + missing_patient_selection 11 = 102 defects)*
**Symptom:** Answers omit a decision threshold, a named comparator, a risk/trade-off, or patient-selection
criteria that the question explicitly requests. **Probable layer:** prompting / model_synthesis (the prompt
may not require structured decision-grade coverage), partly downstream of C1 (missing evidence → missing
comparator). **Causal confidence: medium. Fixability: medium** (a targeted prompt requirement to enumerate
thresholds/comparators/risks, testable on affected questions).

### C3 — Over-absolute / under-qualified language  *(overabsolute_language = 38, minor)*
**Symptom:** Claims insufficiently hedged given evidence uncertainty. **Probable layer:** prompting / synthesis.
**Causal confidence: medium. Fixability: high** (calibration instruction). Low clinical severity but the spec
explicitly prioritizes calibrated uncertainty.

### C4 — Incorrect synthesis / question mis-scoping  *(incorrect_synthesis = 20, material)*
**Symptom:** Misreads question scope (TUMOR-08 interprets "laser" as percutaneous disc decompression, not LITT;
TUMOR-01 misframes supramarginal resection; TUMOR-04 leaves LITT unanswered). **Probable layer:**
query_understanding / synthesis. **Causal confidence: medium. Fixability: low–medium.**

### C5 — Disambiguation scope-narrowing  *(disambiguation_failure = 1 hard, plus soft cases)*
**Symptom:** The disambiguation gate split a deliberately broad question and narrowed it to one limb, then the
re-call returned an **empty answer** — SPINE-02 (cervical+lumbar → "Cervical" → None → the only not-gradable).
Soft variants: SPINE-03 lost true endoscopic-technique coverage to variant narrowing. **Probable layer:**
query_decomposition / disambiguation (`neuro_core/query.py`, `query_analyze.py`) and the runner's
`choose_variant` (longest-label heuristic ≠ "most clinically comprehensive"). **Causal confidence: high**
(directly observed). **Fixability: high** (a narrow reliability fix: never return an empty answer — fall back
to the original/broad question when a disambiguated re-call yields nothing). **Single most cost-effective fix.**

## Cross-cutting notes
- **0 unsafe / 0 safety-critical** across 67 answers: the engine's failure mode is *incompleteness/currency*,
  not dangerous advice. This is the headline safety finding.
- Evidence-verification coverage is honestly low (5/185 anchors verified via PubMed); the rest are
  `verification_unavailable` (training-knowledge grading) — not fabricated.
- C1 and C5 have the highest causal confidence; C5 has the highest fixability-per-impact.
