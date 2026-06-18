# Defect List — Iteration 001

## P0 defects blocking pass

1. **Wrong/degraded routing:** parasagittal meningioma abutting SSS was effectively treated as generic/skull-base rather than supratentorial parasagittal/convexity meningioma.
2. **Parser success did not become operative content:** known facts (right, 4 cm, parasagittal, SSS) did not drive imaging/anatomy/plan/risk sections.
3. **No SSS/bridging-vein safety frame:** absent MRV/CTV, sinus patency/invasion, bridging vein, venous infarct, and sinus bleeding stop-point content.
4. **No operative workflow:** resident/fellow gets no procedure sequence.
5. **No evidence support:** evidence count zero.

## Narrow implementation slice selected

Implement a **parasagittal/SSS meningioma procedure-family default path**, not a broad retrieval redesign:

- Route `right parasagittal 4cm meningioma abutting SSS` to `tumor_convexity_meningioma` / `supratentorial_tumor`.
- Infer only a visibly unverified procedure domain (`meningioma resection / craniotomy prep domain`) from parasagittal/SSS meningioma wording; do not pretend the booked approach is confirmed.
- Render SSS/bridging-vein, MRV/CTV, sinus patency/invasion, motor/SMA, operative sequence, rescue, stop-point, postop watch, and morning-of-case defaults.
- Keep missing facts explicit: booked procedure confirmation, sinus patency/invasion, AP location/eloquence, edema/symptoms, extent-of-resection goal.

## Acceptance criteria

- Generated README shows `Profile: supratentorial_tumor`, not `skull_base`.
- Morning-of-case page names SSS patency/invasion, bridging/cortical veins, AP motor/SMA risk, edema/seizure history, extent-of-resection goal.
- Imaging review requires MRI with contrast and MRV/CTV.
- Anatomy-at-risk names SSS, venous lacunae, bridging veins, cortical veins, motor/sensory cortex, SMA.
- Operative plan includes parasagittal craniotomy, burr-hole/sinus-edge risk, dural opening, devascularization, debulking, extracapsular dissection, sinus-interface stop points, and planned residual option.
- Risk/rescue includes SSS bleeding, venous infarct/sinus thrombosis, dominant bridging-vein injury, seizure/edema, and urgent imaging/ICU escalation.
- Regression tests cover parser routing and renderer content.
