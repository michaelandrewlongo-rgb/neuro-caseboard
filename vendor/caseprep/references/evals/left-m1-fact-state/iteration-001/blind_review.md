# Blind clinical review — left-m1-fact-state iteration 001

## Overall score

**77/100 — PASS** (pass threshold 75/100).

The dossier is clinically useful and mostly safe as a thrombectomy preparation artifact, but it remains generic in several places and misses important late-window, case-specific decision thresholds.

## Category scores

- Technique / operative workflow: **20/25** — strong stepwise EVT workflow, access, guide support, aspiration/stent-retriever/combined technique, clot crossing, pass reassessment, final runs. Weakness: despite supplied transfemoral BGC aspiration plus stent-retriever plan, the dossier repeatedly stays technique-neutral rather than committing to a clear planned combined first-pass sequence.
- Anatomy / dangerous structures: **16/20** — good coverage of ICA terminus, left M1, M2 divisions, lenticulostriates, early branches, access anatomy, tandem disease. Weakness: lacks deeper case-specific anatomy such as dominant hemisphere/language implications, exact ASPECTS regions, collateral pathways, clot length, branch incorporation, and landing-zone detail.
- Complications / rescue plans: **12/15** — covers perforation/SAH, dissection, vasospasm, distal/new-territory emboli, failed recanalization/re-occlusion, access hemorrhage, sICH, malignant edema. Weakness: rescue plans are high-level rather than procedural.
- Alternatives / decision boundaries: **7/10** — includes no-go boundaries, alternate access, no-EVT considerations, tandem/ICAD rescue issues. Weakness: insufficiently explicit for the 10-hour late-window case; DAWN/DEFUSE-3 style criteria and quantitative CTP thresholds are not operationalized.
- Evidence quality and relevance: **8/10** — strong landmark EVT evidence coverage: MR CLEAN, ESCAPE, EXTEND-IA, SWIFT PRIME, REVASCAT, HERMES, DAWN, DEFUSE 3, guidelines, large-core trials. Weakness: evidence is listed more than translated into bedside decision rules.
- Case-specificity: **6/10** — correctly incorporates left M1, NIHSS 18, ASPECTS 7, LKW 10h, CTP mismatch, transfemoral/BGC/aspiration/stent-retriever. Weakness: many sections remain generic or marked needs input; supplied facts do not yet produce a crisp go/no-go and first-pass plan.
- Readability / usability: **4/5** — morning-of-case page and checklists are usable; evidence appendices and repeated abstracts reduce signal-to-noise.
- Provenance / citation support: **4/5** — citations and PMIDs are present and mostly relevant; operative recommendations are not consistently linked to specific evidence/guideline statements.

Total: **77/100**.

## Top 5 clinically important missing or weak items

1. **Late-window quantitative selection criteria are underdeveloped.** For LKW 10h with CTP mismatch, the dossier should force documentation of ischemic core volume, Tmax/hypoperfusion volume, mismatch volume, mismatch ratio, and whether the case fits DAWN/DEFUSE-3/current guideline criteria.
2. **No explicit, case-specific first-pass maneuver.** The input specifies transfemoral BGC aspiration plus stent retriever, but the plan repeatedly offers aspiration-first vs stent-retriever vs combined options. It should state a default planned sequence: femoral access → BGC to cervical ICA → DAC to clot face → microcatheter cross → stent retriever across M1 clot → BGC inflation/proximal aspiration + distal aspiration during retrieval.
3. **Contradictory handling of missing critical facts.** `01-case-summary.md` says “Missing critical facts: none identified,” while other sections flag hemorrhage exclusion, thrombolytic status, baseline mRS/goals of care, CTA confirmation, collaterals, and CTP quantitative data as missing/unknown.
4. **Rescue playbooks need more actionable procedural detail.** Perforation/extravasation rescue should include maintaining position/access, stopping anticoagulants/antiplatelets, protamine if heparinized, balloon tamponade specifics, coil/liquid embolic consideration, emergent CT, and EVD/neurosurgery escalation when needed.
5. **Post-EVT management is reasonable but not sufficiently specific.** BP targets are broad. The dossier should provide institution-adjustable concrete ranges by reperfusion result, hemorrhage/extravasation, thrombolytic exposure, and rescue stent; it should also specify edema surveillance for dominant left MCA infarct and hemicraniectomy triggers.

## Unsafe, misleading, fabricated, contradictory, or overly generic content

- **Contradictory:** “Missing critical facts: none identified” conflicts with missing hemorrhage exclusion, thrombolytic status, baseline mRS, CTA details, collaterals, and CTP metrics.
- **Overly generic:** The operative plan describes general thrombectomy choices instead of committing to the supplied combined BGC aspiration/stent-retriever plan.
- **Potentially misleading:** “CT perfusion mismatch supplied” may be read as sufficient for late-window selection, but quantitative CTP thresholds are still absent.
- **Overly generic evidence use:** Evidence appendices are lengthy/repetitive; lower-applicability corpus items repeat across clinical files.
- **No obvious fabricated citation identified**; major landmark citations appear plausible and relevant.

## Would this help a resident/fellow?

**Yes, moderately.** It would help organize the case, remember safety checks, anticipate common complications, and understand broad EVT workflow. The morning-of-case page is useful. It still requires attending-level supplementation for quantitative late-window eligibility, exact imaging/anatomy, and a concrete first-pass/rescue plan.

## Recommended next product fixes

1. Add late-window EVT eligibility module with onset category, core volume, Tmax >6 sec volume, mismatch ratio/volume, NIHSS-core mismatch, ASPECTS regions, premorbid mRS.
2. Convert supplied technique into a default procedural sequence, with alternatives second.
3. Fix contradiction detection: distinguish “core extracted case facts” from safety-critical unresolved fields; do not say missing critical facts are none when safety-critical facts remain unknown.
4. Make rescue plans operational for perforation/extravasation, dissection, ICAD/re-occlusion, tandem cervical ICA lesion, distal embolus, access-site hemorrhage, malignant edema/sICH.
5. Improve evidence-to-action linkage and reduce repetitive lower-applicability appendices.
