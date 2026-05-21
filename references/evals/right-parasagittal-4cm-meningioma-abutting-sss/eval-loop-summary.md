# CasePrep Eval Loop — right parasagittal 4cm meningioma abutting SSS

## Case input

`right parasagittal 4cm meningioma abutting SSS`

## Score trajectory

- Iteration 001: **9/100 FAIL** — degraded/generic empty scaffold, wrong/generic routing, no usable SSS content.
- Iteration 002: **57/100 FAIL** — major improvement after parasagittal/SSS meningioma defaults, but still below 75 due to shallow SSS decision framework, weak rescue algorithms, and poor evidence synthesis.
- Iteration 003: **58/100 FAIL** — removed irrelevant MEP/SSEP/neuromonitoring language and replaced over-specified framework wording with concise venous-preservation questions; only minimal score gain because remaining blockers are generic placeholders, thin evidence, and abutment-vs-invasion wording.
- Iteration 004: **58/100 FAIL** — fixed main operative-plan placeholder and preserved `abutting SSS; invasion unknown` wording, but score did not move because evidence remains thin and non-operative sections still feel template-like.
- Iteration 005: **84/100 PASS** — added parasagittal/SSS deterministic evidence pack and rendered `Bottom line for this case`; blind review found the dossier operatively useful and evidence synthesis materially improved venous-preservation framing. Remaining defects were patient-specific imaging absence, generic placeholders, high-level SSS bleeding rescue detail, missing study-level numeric takeaways, and evidence provenance inconsistency between live-retrieval count and curated pack.
- Iteration 006: **88/100 PASS** — cleaned evidence provenance, suppressed misleading raw live-retrieval counts from the rendered evidence section, added study-level quantitative takeaways, and added machine-readable curated-pack provenance with 10 source IDs. Blind review found the evidence section clearer and commit-appropriate.

## Current artifact paths

- Iteration 001 output: `/tmp/caseprep-live-right-parasagittal-4cm-meningioma-sss-v1`
- Iteration 002 output: `/tmp/caseprep-live-right-parasagittal-4cm-meningioma-sss-v2`
- Iteration 003 output: `/tmp/caseprep-live-right-parasagittal-4cm-meningioma-sss-v3`
- Iteration 004 output: `/tmp/caseprep-live-right-parasagittal-4cm-meningioma-sss-v4`
- Iteration 005 output: `/tmp/caseprep-live-right-parasagittal-4cm-meningioma-sss-v5`
- Iteration 006 output: `/tmp/caseprep-live-right-parasagittal-4cm-meningioma-sss-v7`
- Saved eval artifacts: `references/evals/right-parasagittal-4cm-meningioma-abutting-sss/`

## Current next best slice

The evidence/provenance slice passed blind review. The next highest-yield slice is operative-plan specificity: add a concise parasagittal/SSS craniotomy and dural-opening strategy keyed to MRV/CTV sinus patency, wall compression versus invasion, venous lacunae, and dominant bridging/cortical veins. Preserve `abutting SSS` as invasion-unknown, and continue avoiding irrelevant MEP/SSEP defaults or a large Sindou-style management matrix.
