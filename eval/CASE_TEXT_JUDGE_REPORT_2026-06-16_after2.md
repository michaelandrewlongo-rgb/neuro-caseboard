# Live Blind Text-Judge — case-dossier quality vs `cases.json` (2026-06-16)

Provider: **vertex**.  Reproduce: `CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_text_judge.py`.

Each dictation -> LLM-authored 8-section dossier (`enrich=False, literature=False`) -> a blind attending-examiner judge grades coverage of every `must_cover` point, red-flag bleed, accuracy, reasoning, and hallucinations. Coverage% is computed from per-point verdicts (covered=1, partial=0.5). **Caveat:** author and judge share the provider model, so this is partly self-grading; the per-point rubric grounding mitigates leniency.

| case | subspecialty | coverage | cov/par/miss | overall | accuracy | safety | bleed | halluc |
|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | 83% | 7/1/1 | 8 | 10 | 9 | 0 | 0 |
| skullbase_vs_retrosigmoid | Skull base / CPA | 89% | 8/0/1 | 9 | 10 | 9 | 0 | 0 |
| functional_awake_glioma | Functional / awake | 67% | 4/4/1 | 7 | 8 | 6 | 0 | 1 |
| vascular_mca_clip | Vascular - open | 89% | 7/2/0 | 8 | 10 | 7 | 0 | 0 |
| neurooncology_convexity_meningioma | Neuro-oncology - non-eloquent tumor | 69% | 5/1/2 | 8 | 9 | 7 | 0 | 0 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric or posterior fossa | 88% | 6/2/0 | 9 | 10 | 9 | 0 | 0 |

## Aggregate
- Mean must-cover coverage: **80.7%**
- Mean overall (judge): **8.2/10**
- Total red-flag bleed incidents: **0**

### spine_acdf_c56 — 83% coverage, overall 8/10
**Missing must-cover:**
- C5 nerve root palsy as a recognized post-decompression deficit
**Top weaknesses:**
- Fails to identify and discuss the risk of postoperative C5 nerve root palsy, a well-known complication of this procedure.
- The description of the fusion construct is incomplete, omitting the critical steps of endplate preparation and the goal of restoring segmental lordosis.
- The management plan for a CSF leak is incomplete, as it omits consideration of a lumbar drain for persistent leaks.

### skullbase_vs_retrosigmoid — 89% coverage, overall 9/10
**Missing must-cover:**
- Internal auditory canal drilling with preservation of the labyrinth/posterior semicircular canal to protect hearing
**Top weaknesses:**
- The dossier's most significant flaw is the complete omission of managing the intracanalicular tumor component, a critical step for a 2.5cm VS. It fails to mention drilling the posterior lip of the internal auditory canal (IAC) and protecting the labyrinth.
- The closure plan lacks detail on cranioplasty (e.g., with titanium mesh or bone cement) to reconstruct the bony defect, which is an important step in preventing pseudomeningocele.

### functional_awake_glioma — 67% coverage, overall 7/10
**Missing must-cover:**
- Neuronavigation with awareness of brain shift; intraoperative ultrasound or imaging adjunct
**Hallucinations:** Claims 'Level II evidence demonstrates that awake craniotomy...' without providing any citation or specific trial, making it an unsupported, generic assertion.
**Top weaknesses:**
- The plan completely fails to account for intraoperative brain shift, a critical variable that renders pre-operative navigation inaccurate. No mitigation strategy (e.g., intraoperative ultrasound) is mentioned.
- The subcortical mapping plan is incomplete, focusing only on the arcuate fasciculus while omitting other critical tracts at risk like the IFOF.
- The anesthesia plan lacks crucial safety and execution details, such as the use of a scalp block for patient comfort or a specific contingency plan for the LMA/airway.
- The discussion of vascular preservation is incomplete, focusing on MCA branches while omitting the critical need to preserve bridging cortical veins.

### vascular_mca_clip — 89% coverage, overall 8/10
**Top weaknesses:**
- Fails to identify the optic nerve and chiasm as key structures at risk during the skull base approach, a critical anatomical omission for a pterional craniotomy.
- The brain relaxation plan is incomplete, omitting standard and often essential techniques like ventriculostomy placement or lamina terminalis fenestration.
- The discussion of post-operative complications and rescue is incomplete, lacking specific plans for managing hydrocephalus or seizures beyond an initial CT scan.

### neurooncology_convexity_meningioma — 69% coverage, overall 8/10
**Missing must-cover:**
- Middle meningeal/external carotid feeding vessels; consider preoperative embolization for a hypervascular tumor
- Anticipated blood loss — type and cross, large-bore IV access
**Top weaknesses:**
- Fails to address specific vascular supply (e.g., MMA) and the standard consideration of preoperative embolization for a large meningioma.
- Omits critical logistical preparations for hemorrhage, such as preparing blood products (type and cross) and ensuring adequate large-bore IV access.
- Incomplete medical management of peritumoral edema; the plan lacks the standard pre-operative administration of dexamethasone.

### pediatric_posterior_fossa_medulloblastoma — 88% coverage, overall 9/10
**Top weaknesses:**
- The oncologic staging plan is incomplete; it mentions spinal imaging but omits the critical timing of post-op brain MRI (within 48h) and the need for CSF cytology.
- The plan lacks some pediatric-specific details, most notably the practice of calculating and tracking allowable blood loss based on the child's weight.
- The neuromonitoring plan is generic; for a fourth ventricle floor tumor, it should specify direct cranial nerve monitoring (e.g., EMG for CN VII, XII) beyond just evoked potentials.

