# Defect list — left-m1-fact-state iteration 001

## Pass gate

- Blind clinical review: **77/100 PASS** (threshold 75).
- No P0 wrong-target/right-M1/basilar leakage identified.
- Supplied NIHSS, ASPECTS, LKW, perfusion, access route, BGC, aspiration, and stent-retriever facts propagated into the live artifact.
- Known live-artifact precheck defects were fixed before review:
  - README no longer says supplied LKW/NIHSS/ASPECTS are pending.
  - `last known well 10 hours ago` renders as `10h`, not `10hours`.

## P0 defects

None blocking this iteration pass.

## P1 defects / next narrow slices

1. **Safety-critical unknowns vs core extracted facts are conflated.**
   - Symptom: `01-case-summary.md` can say “Missing critical facts: none identified,” while hemorrhage exclusion, thrombolytic status, baseline mRS/goals of care, CTA/collateral detail, and quantitative CTP values remain unknown elsewhere.
   - Acceptance: render separate categories: `Core supplied case facts` and `Safety-critical facts still requiring verification`; never label global missing facts as none when safety-critical unknowns remain.

2. **Late-window EVT eligibility is under-operationalized.**
   - Symptom: LKW 10h and CTP mismatch are known, but DAWN/DEFUSE-3/current-guideline quantitative criteria are not turned into a decision checklist.
   - Acceptance: for LKW >6h/late-window phrases or CTP mismatch, require/core prompts for core volume, Tmax/hypoperfusion volume, mismatch volume/ratio, ASPECTS regions, premorbid mRS, and trial/guideline fit.

3. **Supplied technique does not become the default first-pass sequence.**
   - Symptom: dossier lists generic aspiration-first vs stent-retriever vs combined options even when prompt supplies transfemoral BGC aspiration plus stent-retriever.
   - Acceptance: render a default sequence using supplied facts first; alternatives/switch criteria follow second.

4. **Rescue playbooks need procedural detail.**
   - Acceptance: add actionable sequences for perforation/extravasation, dissection, ICAD/re-occlusion, tandem lesion, distal embolus, access-site hemorrhage, malignant edema/sICH.

5. **Evidence-to-action linkage remains weak.**
   - Acceptance: evidence section should include “applicable because,” “not applicable unless,” “decision threshold,” and “what this changes in the plan,” and keep lower-applicability source dumps out of core clinical files.

## Recommended next implementation slice

Start with P1 #1 and #2 together only if kept narrow: a deterministic `safety_critical_unknowns` projection for thrombectomy plus late-window eligibility checklist. This directly addresses the main contradiction and the largest remaining clinical decision-boundary gap.
