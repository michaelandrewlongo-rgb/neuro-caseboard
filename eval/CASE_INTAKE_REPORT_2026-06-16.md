# Case Intake Eval — WS-1 (2026-06-16)

Reproduce: `python3 eval/intake_eval.py`. Ground truth: `eval/case_dictations.json`.

- **Deterministic extraction** (side/level) is real and fully offline — the no-model floor.
- **Goal / comorbidities / missing_critical==0** validate the full parse/merge path fed the
  ground-truth JSON (an injected fake) — they prove *capture*, not model quality.
- **Live model-quality blind grade: DEFERRED** — no provider key in CI/this environment
  (consistent with the skipped live-PubMed test). Re-run with `CASEBOARD_LLM_PROVIDER` set
  to grade the model's own extraction.

| case | subspecialty | side (det) | level (det) | goal | comorbid | det missing_critical | complete→0 |
|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | right OK | C5-6 OK | OK | OK | 2 | OK |
| spine_l4l5_tlif | Spine | right OK | L4-5 OK | OK | OK | 2 | OK |
| spine_lumbar_microdisc_l5s1 | Spine | left OK | L5-S1 OK | OK | OK | 2 | OK |
| spine_thoracic_intradural_meningioma_t6 | Spine | left OK | T6 OK | OK | OK | 2 | OK |
| skullbase_vs_retrosigmoid | Skull base | left OK | - OK | OK | OK | 3 | OK |
| skullbase_petroclival_meningioma | Skull base | right OK | - OK | OK | OK | 3 | OK |
| skullbase_pituitary_endonasal | Skull base | midline OK | - OK | OK | OK | 3 | OK |
| skullbase_cpa_epidermoid | Skull base | left OK | - OK | OK | OK | 3 | OK |
| vascular_mca_clip | Vascular | left OK | - OK | OK | OK | 3 | OK |
| vascular_acom_clip | Vascular | right OK | - OK | OK | OK | 3 | OK |
| vascular_pcom_clip | Vascular | left OK | - OK | OK | OK | 3 | OK |
| vascular_avm_resection | Vascular | right OK | - OK | OK | OK | 3 | OK |
| endovascular_acom_coiling | Vascular | midline OK | - OK | OK | OK | 3 | OK |
| endovascular_basilar_coiling | Vascular | midline OK | - OK | OK | OK | 3 | OK |
| endovascular_ica_flow_diverter | Vascular | right OK | - OK | OK | OK | 3 | OK |
| endovascular_mca_thrombectomy | Vascular | left OK | - OK | OK | OK | 3 | OK |
| functional_awake_glioma | Functional | left OK | - OK | OK | OK | 3 | OK |
| functional_dbs_stn_parkinsons | Functional | bilateral OK | - OK | OK | OK | 3 | OK |
| functional_temporal_lobectomy_epilepsy | Functional | left OK | - OK | OK | OK | 3 | OK |
| neurooncology_convexity_meningioma | Neuro-oncology | right OK | - OK | OK | OK | 3 | OK |
| neurooncology_gbm_temporal | Neuro-oncology | right OK | - OK | OK | OK | 3 | OK |
| neurooncology_cerebellar_metastasis | Neuro-oncology | right OK | - OK | OK | OK | 3 | OK |
| neurooncology_intraventricular_tumor | Neuro-oncology | left OK | - OK | OK | OK | 3 | OK |
| pediatric_posterior_fossa_medulloblastoma | Pediatric | midline OK | - OK | OK | OK | 3 | OK |
| pediatric_cerebellar_pilocytic_astrocytoma | Pediatric | left OK | - OK | OK | OK | 3 | OK |
| pediatric_craniopharyngioma | Pediatric | midline OK | - OK | OK | OK | 3 | OK |
| pediatric_myelomeningocele_closure | Pediatric | midline OK | - OK | OK | OK | 3 | OK |

## Scores
- Deterministic side: **27/27**
- Deterministic level: **27/27**
- Goal captured (parse path): **27/27**
- Comorbidities captured (parse path): **27/27**
- `missing_critical()==0` on complete record: **27/27**
- `missing_critical()<=3` on deterministic parse: **27/27**

**WS-1 acceptance: MET** (side/level extracted, goal+comorbidities captured, missing_critical conservative).
