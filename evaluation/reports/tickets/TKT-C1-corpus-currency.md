# TKT-C1 — Corpus evidence-currency gap (predates 2022–2025 practice-changing evidence)

- **Failure-mode ID / category:** C1 / `outdated_evidence` + `retrieval_omission`
- **Severity / priority:** material / **P1** (priority 200; highest *impact* — 245/406 defects, 60%)
- **Labels:** `severity:material` `subsystem:retrieval` `subsystem:corpus` `stage:retrieval` `status:deferred`
- **Affected questions (non-exhaustive):** NIS-01/02/05, GENERAL-01/04/05, FUNCTIONAL-01/04/05, TRAUMA-01/02/03/06/10, SPINE-01, TUMOR-05.
- **Artifact links:** `evaluation/reports/root-causes/C1-corpus-currency.md`, `failure-analysis.md` (C1), `failure-ledger.jsonl`.

## Observed vs expected
- **Observed:** answers omit or mis-date named, practice-changing trials/approvals (ESCAPE-MeVO, SELECT2/ANGEL-ASPECT, the MMA-embolization RCTs, ENRICH, MRgFUS approvals, SANTE, RESCUEicp, GFAP/UCH-L1, SLIP/NORDSTEN-DS, JLGK0901). Several grader anchors were PubMed-verified.
- **Expected:** answers reflect current primary evidence for the contemporary questions.

## Impact
Caps scores across all domains; the single largest driver of B/C/D grades. **Clinically safe** (no unsafe answers), but not current.

## Suspected layer & causal confidence
retrieval / corpus source coverage. The corpus is a static textbook RAG index predating these sources; retrieval cannot surface what the corpus lacks. **Causal confidence: high** (publication dates objective). A literature/PubMed lane exists (`neuro_caseboard/literature/`) but is additive and does not currently inject recent trial evidence into the primary synthesis for these questions.

## Why DEFERRED (not fixed this pass)
Remediation (enable/strengthen the literature lane to inject 2022–2025 evidence into synthesis) is a **large, network-dependent** change with real regression and latency risk for a 67-question rerun. Rushing it would jeopardize the "no unexplained regression / acceptable latency" success criteria. Recorded as the top deferred item with a concrete remediation surface; to be done as its own focused effort.

## Acceptance criteria (for the future effort)
Measurable lift on the affected questions WITHOUT new safety-critical errors, acceptable added latency, and the literature lane's injected evidence correctly cited. Requires its own baseline-comparable rerun.
