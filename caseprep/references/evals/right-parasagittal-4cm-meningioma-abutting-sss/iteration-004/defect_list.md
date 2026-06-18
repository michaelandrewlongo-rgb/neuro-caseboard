# Iteration 004 defect list

## Materially improved

- Main operative plan no longer starts with `Approach: needs input` / `Rationale: needs input`.
- Diagnosis now preserves uncertainty: `right 4cm parasagittal meningioma abutting superior sagittal sinus (SSS); invasion unknown`.
- Search check found no `superior sagittal sinus meningioma` overcall, MEP/SSEP, or neuromonitoring language in the generated markdown.

## Blind review score

- Overall: 58/100 FAIL (threshold 75)
- Delta from iteration 003: 0

## Interpretation

This slice fixed the specific product defect but did not move the clinical score. Remaining score bottlenecks are now structural/content depth, especially evidence retrieval/synthesis and persistent generic placeholders in non-operative sections.

## P0/P1 defects

### P0 — still blocks pass

1. Evidence section is nonfunctional: one source, no synthesis, no source hierarchy.
2. Many non-operative sections remain template-like `needs input` blocks rather than useful must-verify case questions.
3. Operative specificity remains limited: craniotomy/dural-opening/falx/sinus-repair details are still too generic.

### P1

1. Add structured venous imaging readout fields without inventing facts.
2. Add concise practical rescue cards for SSS bleeding / bridging vein injury / venous infarct / air embolism.
3. Add nuanced alternatives: SRS/fractionated RT limitations for 4 cm lesions, residual sinus disease, and observation thresholds.

## Next narrow slice recommendation

The biggest score bottleneck is now evidence retrieval/synthesis, not more hand-authored defaults.

Recommended next slice:

**Improve parasagittal/SSS meningioma evidence retrieval and render a concise bottom-line evidence section.**

Acceptance criteria:

- `07-evidence.md` has more than one source for this case.
- Evidence is grouped into clinically useful buckets: SSS/parasagittal outcomes, venous complications/bridging veins, residual/adjuvant radiation, and recurrence/EOR.
- `07-evidence.md` contains a short `Bottom line for this case` paragraph, not just raw source dump.
- Avoid claiming invasion or recommending a giant Sindou matrix; preserve abutment/invasion uncertainty.
- Continue excluding MEP/SSEP unless the user explicitly asks.
