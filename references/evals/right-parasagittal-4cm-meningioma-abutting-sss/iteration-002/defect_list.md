# Defect List — Iteration 002

## Improved from iteration 001

- Routed the case to `tumor_convexity_meningioma` / `supratentorial_tumor` instead of degraded/generic skull-base output.
- Propagated right, 4 cm, parasagittal, and SSS facts into the dossier.
- Added morning-of-case SSS/bridging-vein/MRV/CTV/extent-of-resection prompts.
- Added imaging, anatomy-at-risk, operative-plan, risk/rescue, and postop defaults for parasagittal/SSS meningioma.
- Added regression coverage for parser routing and renderer content.

## Remaining P0/P1 defects

### P0/P1: SSS decision framework still too shallow

Need a practical decision tree around:

- abutment only
- compression/narrowing with preserved flow
- wall invasion with patent sinus
- partial occlusion
- complete/collateralized occlusion
- dominant bridging-vein dependence

Each should map to resection, peel/coagulate, reconstruct/patch, leave residual, or adjuvant RT/SRS strategy.

### P1: rescue algorithms need steps

Need actionable algorithms for:

- SSS/lacuna bleeding
- dominant bridging-vein injury
- venous air embolism
- MEP/SSEP loss / new motor deficit
- intraoperative swelling/venous congestion
- postop seizure/status
- venous infarct/sinus thrombosis

### P1: evidence is now the score bottleneck

Only one PubMed source was retrieved. Need a curated/evidence-pack fallback for parasagittal/SSS meningioma: surgical series/reviews on sinus invasion, Sindou classification, Simpson grade vs recurrence, subtotal + SRS/RT, venous complications, embolization selection.

## Recommended next narrow slice

Do **not** move to dashboard/visuals. Next best slice: **SSS invasion decision tree + venous rescue algorithms** in the parasagittal meningioma module, with tests asserting those sections appear in morning-of-case, operative plan, and risk/rescue. Then run iteration 003 blind review. Evidence-pack retrieval is likely the next slice after that.
