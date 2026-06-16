# Live Blind Text-Judge — case-dossier quality vs `cases.json` (2026-06-16)

Provider: **vertex**.  Reproduce: `CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_text_judge.py`.

Each dictation -> LLM-authored 8-section dossier (`enrich=False, literature=False`) -> a blind attending-examiner judge grades coverage of every `must_cover` point, red-flag bleed, accuracy, reasoning, and hallucinations. Coverage% is computed from per-point verdicts (covered=1, partial=0.5). **Caveat:** author and judge share the provider model, so this is partly self-grading; the per-point rubric grounding mitigates leniency.

| case | subspecialty | coverage | cov/par/miss | overall | accuracy | safety | bleed | halluc |
|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | 83% | 7/1/1 | 8 | 10 | 8 | 0 | 0 |
| skullbase_vs_retrosigmoid | Skull base / CPA | 67% | 5/2/2 | 7 | 10 | 7 | 0 | 0 |
| functional_awake_glioma | Functional / awake | 72% | 4/5/0 | 7 | 9 | 7 | 0 | 0 |
| vascular_mca_clip | Vascular - open | 89% | 7/2/0 | 9 | 10 | 8 | 0 | 0 |
| neurooncology_convexity_meningioma | Neuro-oncology - non-eloquent tumor | 75% | 4/4/0 | 8 | 10 | 7 | 0 | 1 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric or posterior fossa | 31% | 1/3/4 | 1 | 5 | 1 | 1 | 0 |

## Aggregate
- Mean must-cover coverage: **69.6%**
- Mean overall (judge): **6.7/10**
- Total red-flag bleed incidents: **1**

### spine_acdf_c56 — 83% coverage, overall 8/10
**Missing must-cover:**
- Vertebral artery injury if dissection or uncovertebral/foraminotomy drilling is carried too far laterally
**Top weaknesses:**
- The vertebral artery is never mentioned as a structure-at-risk, which is a critical omission given the plan for foraminotomy.
- The management plan for a dural tear is incomplete; it lacks consideration for a lumbar drain, a standard adjunct for significant CSF leaks.
- While 'sagittal alignment' is mentioned, explicitly stating the goal of restoring segmental 'lordosis' would be more precise for a cervical case.

### skullbase_vs_retrosigmoid — 67% coverage, overall 7/10
**Missing must-cover:**
- Trigeminal nerve (CN V) at the superior tumor pole
- Lower cranial nerves (IX, X, XI) at the caudal pole
**Top weaknesses:**
- Incomplete anatomical risk assessment: The plan completely omits the trigeminal nerve (CN V) and lower cranial nerves (IX, X, XI) as structures at risk.
- Insufficient technical detail for hearing preservation: The plan for IAC drilling lacks the crucial step of identifying and preserving the labyrinth/semicircular canals.
- Failure to identify all key structures at risk: A complete plan must account for all cranial nerves in the operative field, not just the facial and cochlear nerves.

### functional_awake_glioma — 72% coverage, overall 7/10
**Top weaknesses:**
- Fails to address brain shift: The plan relies heavily on neuronavigation but omits the critical limitation of brain shift and any mitigation strategy like intraoperative ultrasound.
- Incomplete mapping plan: The plan omits subcortical mapping of the corticospinal tracts and other relevant language tracts like the IFOF, focusing only on the arcuate fasciculus.
- Lacks anesthetic detail: While naming the 'asleep-awake-asleep' technique, it lacks crucial details such as the plan for a scalp block or specific airway management contingencies.

### vascular_mca_clip — 89% coverage, overall 9/10
**Top weaknesses:**
- The brain relaxation plan is incomplete; it mentions mannitol but omits the critical neurosurgical step of draining CSF from the basal cisterns.
- The plan fails to identify the optic nerve and chiasm as specific, critical structures-at-risk during the pterional approach and dissection.

### neurooncology_convexity_meningioma — 75% coverage, overall 8/10
**Hallucinations:** No specific fabricated data points (e.g., invented measurements, fake citations) were identified.
**Top weaknesses:**
- Fails to mention the use of corticosteroids (dexamethasone) for management of significant peritumoral edema, a standard-of-care intervention.
- The plan for a Simpson Grade I resection is incomplete, as it omits the necessary step of resecting involved or hyperostotic bone.
- The vascular plan is superficial; it fails to identify the likely arterial supply (MMA/ECA) and does not discuss the critical decision of whether to pursue preoperative embolization.

### pediatric_posterior_fossa_medulloblastoma — 31% coverage, overall 1/10
**Missing must-cover:**
- Fourth ventricle floor and brainstem with facial colliculus preservation
- Lower cranial nerves (IX, X, XII) at the floor — swallow/airway function and risk of postoperative bulbar dysfunction
- PICA and tonsillar/brainstem perforator preservation
- Oncologic staging — postoperative MRI within 48 hours plus neuraxis MRI and CSF cytology for leptomeningeal spread
**Red-flag bleed:** R1 @ When to abort: uncontrolled VA/carotid bleeding...
**Top weaknesses:**
- The dossier is a generic template, not a specific plan; it asks questions rather than providing answers.
- Fails to identify case-specific anatomy at risk, such as the floor of the fourth ventricle, facial colliculus, lower cranial nerves, and PICA.
- Completely omits critical pediatric considerations, particularly weight-based blood volume and anesthetic management.
- Lacks any discussion of the required oncologic staging (post-op neuraxis imaging, CSF cytology), which is fundamental for medulloblastoma.

