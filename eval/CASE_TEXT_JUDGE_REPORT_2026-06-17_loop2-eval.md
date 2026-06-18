# Live Blind Text-Judge — case-dossier quality vs `cases.json` (2026-06-17)

Provider: **vertex**.  Reproduce: `CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_text_judge.py`.

Each dictation -> LLM-authored 8-section dossier (`enrich=False, literature=False`) -> a blind attending-examiner judge grades coverage of every `must_cover` point, red-flag bleed, accuracy, reasoning, and hallucinations. Coverage% is computed from per-point verdicts (covered=1, partial=0.5). **Caveat:** author and judge share the provider model, so this is partly self-grading; the per-point rubric grounding mitigates leniency.

| case | subspecialty | coverage | cov/par/miss | overall | accuracy | safety | bleed | halluc |
|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | 83% | 7/1/1 | 9 | 9 | 10 | 0 | 0 |
| spine_lumbar_microdisc_l5s1 | Spine | 100% | 8/0/0 | 10 | 10 | 10 | 0 | 0 |
| spine_thoracic_intradural_meningioma_t6 | Spine | 56% | 4/1/3 | 7 | 9 | 6 | 0 | 0 |
| skullbase_petroclival_meningioma | Skull base / CPA | 81% | 5/3/0 | 6 | 9 | 5 | 0 | 0 |
| skullbase_pituitary_endonasal | Skull base / CPA | 69% | 4/3/1 | 8 | 10 | 8 | 0 | 0 |
| vascular_acom_clip | Vascular - open | 81% | 6/1/1 | 9 | 10 | 8 | 0 | 0 |
| vascular_pcom_clip | Vascular - open | 88% | 7/0/1 | 10 | 10 | 10 | 0 | 0 |
| vascular_avm_resection | Vascular - open | 75% | 5/2/1 | 9 | 10 | 8 | 0 | 0 |
| endovascular_basilar_coiling | Vascular - endovascular | 75% | 5/2/1 | 8 | 9 | 7 | 0 | 0 |
| endovascular_ica_flow_diverter | Vascular - endovascular | 69% | 3/5/0 | 7 | 10 | 7 | 0 | 0 |
| endovascular_mca_thrombectomy | Vascular - endovascular | 88% | 6/2/0 | 9 | 10 | 8 | 0 | 0 |
| functional_awake_glioma | Functional / awake | 89% | 7/2/0 | 9 | 10 | 9 | 0 | 0 |
| functional_temporal_lobectomy_epilepsy | Functional / awake | 100% | 8/0/0 | 10 | 10 | 10 | 0 | 0 |
| neurooncology_gbm_temporal | Neuro-oncology | 81% | 6/1/1 | 9 | 10 | 8 | 0 | 0 |
| neurooncology_cerebellar_metastasis | Neuro-oncology | 88% | 6/2/0 | 8 | 9 | 10 | 0 | 0 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric / posterior fossa | 88% | 6/2/0 | 9 | 10 | 10 | 0 | 0 |
| pediatric_cerebellar_pilocytic_astrocytoma | Pediatric / posterior fossa | 94% | 7/1/0 | 9 | 10 | 10 | 0 | 0 |
| pediatric_myelomeningocele_closure | Pediatric / posterior fossa | 88% | 7/0/1 | 8 | 10 | 6 | 0 | 0 |

## Aggregate
- Mean must-cover coverage: **82.8%**
- Mean overall (judge): **8.6/10**
- Total red-flag bleed incidents: **0**

### spine_acdf_c56 — 83% coverage, overall 9/10
**Missing must-cover:**
- C5 nerve root palsy as a recognized post-decompression deficit
**Top weaknesses:**
- Fails to identify C5 nerve root palsy as a known, albeit uncommon, risk of the planned anterior operation itself, instead attributing it only to the posterior alternative.
- The management plan for a dural tear/CSF leak is incomplete; it mentions primary repair but omits the contingency plan for a lumbar drain.
- The dossier is verbose and repetitive; the constant 'Why:' annotations, while demonstrating thought, are unnecessary for a professional summary and could be integrated more concisely.

### spine_lumbar_microdisc_l5s1 — 100% coverage, overall 10/10
**Top weaknesses:**
- Fails to explicitly mention padding of all pressure points (face, eyes, bony prominences) as part of the prone positioning plan.
- Lacks specific, case-derived details from the MRI, such as disc fragment morphology (e.g., extrusion, sequestration) or migration, which would refine the operative plan.

### spine_thoracic_intradural_meningioma_t6 — 56% coverage, overall 7/10
**Missing must-cover:**
- Dentate ligament division and gentle cord rotation for ventral/ventrolateral tumor access
- Preservation of segmental radicular arteries (artery of Adamkiewicz territory) to avoid cord ischemia
- Postoperative kyphosis/instability consideration if extensive laminectomy — fusion contingency
**Top weaknesses:**
- Omission of key intradural maneuvers: The plan fails to mention division of the dentate ligaments, a critical step for safely mobilizing the spinal cord to access a ventrolateral tumor.
- Inadequate vascular risk assessment: The dossier does not mention the risk to segmental radicular arteries (e.g., Artery of Adamkiewicz territory), a crucial consideration for avoiding spinal cord ischemia.
- Failure to address biomechanical stability: The plan for a potential multi-level laminectomy (T5-T7) completely omits the significant risk of post-operative kyphosis and the potential need for instrumented fusion.

### skullbase_petroclival_meningioma — 81% coverage, overall 6/10
**Top weaknesses:**
- Fails to mention venous air embolism (VAE) precautions, a critical safety consideration for the lateral decubitus position.
- The CSF leak prevention plan is incomplete; it mentions dural closure but omits the essential step of waxing mastoid air cells.
- The plan lacks detail on managing the lower cranial nerves (IX, X, XI), failing to specify their location or the functional risks of injury (e.g., dysphagia).
- The description of the bony approach is superficial, omitting any mention of petrous bone drilling which is often required for adequate exposure.

### skullbase_pituitary_endonasal — 69% coverage, overall 8/10
**Missing must-cover:**
- Postoperative epistaxis and sinonasal morbidity counseling
**Top weaknesses:**
- The CSF leak management plan is incomplete; it describes intraoperative repair but omits the standard postoperative contingency of lumbar drainage for persistent leaks.
- The dossier fails to address common sinonasal morbidity, specifically the risk of postoperative epistaxis and the need for patient counseling on this topic.
- While cavernous sinus invasion is mentioned as a limit to resection, the specific cranial nerves (III, IV, V1/V2, VI) contained within are not enumerated as structures at risk.

### vascular_acom_clip — 81% coverage, overall 9/10
**Missing must-cover:**
- Gyrus rectus resection for exposure when needed and avoidance of frontal lobe injury
**Top weaknesses:**
- The surgical plan for exposure omits the gyrus rectus resection maneuver, a key step for visualizing the ACOM complex without undue frontal lobe retraction.
- The postoperative plan correctly addresses vasospasm but fails to mention surveillance and management for hyponatremia/cerebral salt wasting, a common and critical post-SAH complication.

### vascular_pcom_clip — 88% coverage, overall 10/10
**Missing must-cover:**
- Post-SAH vasospasm risk and nimodipine if ruptured
**Top weaknesses:**
- The plan correctly identifies the aneurysm as unruptured but fails to discuss the management of post-SAH vasospasm, which would be a critical sequela of a major intraoperative rupture.
- While a lumbar drain is mentioned, the plan does not explicitly state that opening basal cisterns (e.g., opticocarotid, lamina terminalis) is a primary intraoperative technique for CSF drainage and brain relaxation.
- The case title contains a repetitive typographical error ('left left posterior communicating artery left posterior communicating artery'), indicating a lack of final proofreading.

### vascular_avm_resection — 75% coverage, overall 9/10
**Missing must-cover:**
- Brain relaxation and meticulous staged hemostasis throughout
**Top weaknesses:**
- The plan omits the gold-standard postoperative DSA to definitively confirm complete AVM obliteration, relying only on intraoperative adjuncts.
- Fails to explicitly plan for brain relaxation (e.g., mannitol, CSF drainage), a key maneuver for managing brain swelling and improving surgical exposure.
- Does not describe the classic surgical sequence of managing deep perforating feeders as the hazardous final step of the dissection.

### endovascular_basilar_coiling — 75% coverage, overall 8/10
**Missing must-cover:**
- Working projections to define the neck and protect both P1 origins
**Top weaknesses:**
- Fails to specify the use of a triaxial system (guide, intermediate, microcatheter), which is critical for support and stability when accessing the basilar apex.
- Lacks any mention of selecting or using specific 2D 'working projections' to visualize the aneurysm neck and parent vessel origins, a fundamental step for safe device deployment.
- Completely omits radiation and contrast dose stewardship (e.g., ALARA, contrast limits), which are essential components of patient safety in neurointerventional procedures.

### endovascular_ica_flow_diverter — 69% coverage, overall 7/10
**Top weaknesses:**
- Fails to discuss management of delayed risks, such as strict blood pressure control for delayed rupture or steroid consideration for worsening mass effect during thrombosis.
- Omits any mention of radiation or contrast stewardship (e.g., minimizing fluoro time, contrast load), a key aspect of patient safety.
- The discussion of side-branch risk is incomplete, focusing only on the ophthalmic artery while ignoring other critical perforators that may be involved.
- The access plan is generic and lacks detail regarding the specific challenges of navigating the carotid siphon or the full composition of the access system (i.e., triaxial).

### endovascular_mca_thrombectomy — 88% coverage, overall 9/10
**Top weaknesses:**
- The plan to mitigate distal embolization is incomplete; it mentions aspiration but omits the use of a balloon-guide catheter for proximal flow arrest.
- The post-operative surveillance plan is vague, lacking a schedule for routine neurological checks and standard 24-hour imaging to screen for hemorrhagic transformation.

### functional_awake_glioma — 89% coverage, overall 9/10
**Top weaknesses:**
- The subcortical mapping plan fails to mention the Inferior Fronto-Occipital Fasciculus (IFOF), a key language pathway at risk in this location.
- The anesthesia plan omits a scalp block, which is a critical component for ensuring patient comfort and cooperation during the awake phase.
- While risks to the motor system are noted, the plan could be more explicit about the technique for subcortical mapping of the corticospinal tract at the posterior resection margin.

### functional_temporal_lobectomy_epilepsy — 100% coverage, overall 10/10
**Top weaknesses:**
- Fails to explicitly name the oculomotor nerve (CN III) as a specific structure at risk during the mesial resection, despite correctly identifying its surrounding anatomical boundaries.
- While mentioning intraoperative ECoG, it does not provide a clear decision-making algorithm based on its findings (e.g., criteria for extending the resection if post-resection spikes persist).

### neurooncology_gbm_temporal — 81% coverage, overall 9/10
**Missing must-cover:**
- Brain shift during resection degrading navigation — intraoperative ultrasound/imaging adjunct
**Top weaknesses:**
- Fails to account for intraoperative brain shift, which degrades the accuracy of the pre-operative MRI-based neuronavigation plan.
- Omits discussion of preserving critical venous anatomy during the craniotomy, specifically the vein of Labbé and the transverse/sigmoid sinus complex.
- Lacks a definitive plan for intraoperative neuromonitoring, mentioning it only as a possibility ('if used') without specifying modalities.

### neurooncology_cerebellar_metastasis — 88% coverage, overall 8/10
**Top weaknesses:**
- The dossier presents a conflicting tumor resection strategy, describing both circumferential dissection (implying en bloc) and internal debulking without explaining the oncologic rationale or decision criteria.
- The plan for managing posterior fossa pressure focuses on hydrocephalus and hematoma but omits the specific risk and management of postoperative cerebellar swelling.
- The dossier fails to mention the need for preoperative systemic oncologic staging (e.g., PET/CT) to confirm the metastasis is solitary, a key part of the indication for surgery.

### pediatric_posterior_fossa_medulloblastoma — 88% coverage, overall 9/10
**Top weaknesses:**
- The oncologic staging plan is incomplete; it mentions pre-operative spine MRI but omits the mandatory post-operative brain MRI within 48 hours and CSF cytology for definitive staging.
- The cranial nerve risk assessment is incomplete; it correctly identifies risks to CN VI, VII, IX, and X but omits the risk to CN XII (hypoglossal nerve), which is also vulnerable.

### pediatric_cerebellar_pilocytic_astrocytoma — 94% coverage, overall 9/10
**Top weaknesses:**
- The plan lacks specific anatomical detail regarding the deep cerebellum; it mentions 'deep cerebellar nuclei' but fails to name the dentate nucleus or the cerebellar peduncles, which are the critical structures at risk.
- While EVD is mentioned, the plan omits any discussion of Endoscopic Third Ventriculostomy (ETV) as a potential management strategy for the obstructive hydrocephalus.
- The dossier is generic and reads like a textbook chapter; it lacks specific measurements or nuanced details from the patient's actual imaging that would tailor the plan more precisely.

### pediatric_myelomeningocele_closure — 88% coverage, overall 8/10
**Missing must-cover:**
- Avoidance/limitation of latex exposure given latex-allergy risk in spina bifida
**Top weaknesses:**
- Critical Omission of Latex Allergy: The dossier completely fails to mention the high incidence of latex allergy in the spina bifida population and the corresponding need for latex-free precautions.
- No Mention of Post-operative Positioning: Fails to specify the crucial post-operative plan to keep the infant prone to protect the fragile wound from pressure and contamination.
- Vague on Neuromonitoring Specifics: While EMG is mentioned, the plan lacks specifics on which myotomes/muscles (e.g., anal sphincter) will be monitored to map specific sacral nerve roots.

