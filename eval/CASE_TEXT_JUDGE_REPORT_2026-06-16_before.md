# Live Blind Text-Judge — case-dossier quality vs `cases.json` (2026-06-16)

Provider: **vertex**.  Reproduce: `CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_text_judge.py`.

Each dictation -> LLM-authored 8-section dossier (`enrich=False, literature=False`) -> a blind attending-examiner judge grades coverage of every `must_cover` point, red-flag bleed, accuracy, reasoning, and hallucinations. Coverage% is computed from per-point verdicts (covered=1, partial=0.5). **Caveat:** author and judge share the provider model, so this is partly self-grading; the per-point rubric grounding mitigates leniency.

| case | subspecialty | coverage | cov/par/miss | overall | accuracy | safety | bleed | halluc |
|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | 56% | 4/2/3 | 6 | 9 | 3 | 0 | 0 |
| skullbase_vs_retrosigmoid | Skull base / CPA | 72% | 6/1/2 | 8 | 10 | 7 | 0 | 0 |
| functional_awake_glioma | Functional / awake | 72% | 5/3/1 | 6 | 10 | 4 | 0 | 0 |
| vascular_mca_clip | Vascular - open | 72% | 5/3/1 | 6 | 10 | 5 | 0 | 0 |
| neurooncology_convexity_meningioma | Neuro-oncology - non-eloquent tumor | 56% | 3/3/2 | 7 | 9 | 6 | 0 | 0 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric or posterior fossa | 62% | 3/4/1 | 5 | 8 | 5 | 0 | 0 |

## Aggregate
- Mean must-cover coverage: **65.2%**
- Mean overall (judge): **6.3/10**
- Total red-flag bleed incidents: **0**

### spine_acdf_c56 — 56% coverage, overall 6/10
**Missing must-cover:**
- Esophageal/pharyngeal perforation risk with retractor blade placement
- C5 nerve root palsy as a recognized post-decompression deficit
- Expanding postoperative neck hematoma causing airway compromise — emergent bedside wound evacuation and reintubation as rescue
**Top weaknesses:**
- Critically fails to identify and plan for a postoperative expanding neck hematoma, the most immediate life-threatening complication of this surgery.
- Omits several key intraoperative risks and their management, including esophageal perforation, a plan for durotomy repair, and C5 nerve root palsy.
- The surgical technique for the fusion construct is incomplete, lacking mention of endplate preparation and the goal of restoring segmental lordosis.

### skullbase_vs_retrosigmoid — 72% coverage, overall 8/10
**Missing must-cover:**
- Trigeminal nerve (CN V) at the superior tumor pole
- Lower cranial nerves (IX, X, XI) at the caudal pole
**Top weaknesses:**
- Fails to identify or plan for cranial nerves V (trigeminal) at the superior pole and IX, X, XI (lower cranial nerves) at the inferior pole, which are critical structures at risk for a 2.5 cm tumor.
- Lacks detail on managing the intrameatal portion of the tumor, omitting the common necessity of drilling the internal auditory canal and the associated risk to the labyrinth.
- The plan is generic and does not incorporate specific findings from the patient's imaging, such as the anticipated location of the facial nerve or AICA loop based on the FIESTA MRI.

### functional_awake_glioma — 72% coverage, overall 6/10
**Missing must-cover:**
- MCA/Sylvian branch and cortical vein preservation
**Top weaknesses:**
- Fails to explicitly mention preservation of critical vasculature, such as MCA branches and cortical veins, a major safety omission for this approach.
- Lacks specificity in subcortical mapping; fails to name the critical white matter tracts at risk (e.g., arcuate fasciculus, SLF, IFOF).
- The anesthesia plan is incomplete; it omits key details like the use of a scalp block for analgesia and specific airway management (e.g., LMA).

### vascular_mca_clip — 72% coverage, overall 6/10
**Missing must-cover:**
- Adenosine-induced transient flow arrest as a rescue for a difficult or prematurely ruptured neck
**Top weaknesses:**
- Fails to detail critical techniques for achieving brain relaxation, such as CSF drainage from basal cisterns or lamina terminalis.
- Omits adenosine-induced transient flow arrest, a key chemical adjunct for managing a difficult or prematurely ruptured aneurysm neck.
- Fails to identify the optic nerve and chiasm as critical structures at risk during the pterional approach and sphenoid wing drilling.

### neurooncology_convexity_meningioma — 56% coverage, overall 7/10
**Missing must-cover:**
- Middle meningeal/external carotid feeding vessels; consider preoperative embolization for a hypervascular tumor
- Anticipated blood loss — type and cross, large-bore IV access
**Top weaknesses:**
- Critically omits logistical preparation for major blood loss, such as ensuring blood products are typed and crossed and that large-bore IV access is established.
- Fails to address preoperative planning for a hypervascular tumor, omitting any mention of feeding vessels (e.g., MMA) or the option of embolization.
- Lacks a plan for routine early postoperative imaging, which is essential for detecting a postoperative hematoma (a stated catastrophic risk).
- The plan for steroid management is reactive ('if edema worsens') rather than proactive (stating a plan for pre-operative administration).

### pediatric_posterior_fossa_medulloblastoma — 62% coverage, overall 5/10
**Missing must-cover:**
- PICA and tonsillar/brainstem perforator preservation
**Top weaknesses:**
- Vascular Anatomy Omission: The plan completely fails to mention the Posterior Inferior Cerebellar Artery (PICA), the most critical vessel in the telovelar approach.
- Incomplete Functional Anatomy: Lacks specific landmarks (facial colliculus) and fails to connect nerve risks (CN IX, X) to specific functional deficits (bulbar palsy).
- Missing Key Risks: Fails to identify the classic risk of venous air embolism (VAE) in prone posterior fossa surgery or pediatric-specific blood loss accounting.
- Incomplete Oncologic Plan: Omits the standard-of-care postoperative MRI within 48 hours for extent-of-resection assessment and CSF cytology for staging.

