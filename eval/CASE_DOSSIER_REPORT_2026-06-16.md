# Case Dossier Section-Coverage + Literature Eval — WS-2/WS-3 (2026-06-16)

Reproduce: `python3 eval/case_eval.py`. Ground truth: `eval/case_dictations.json`.

Checks all eight LOOP_PROMPT §0 surfaces render and (WS-3) that the three reasoning-bearing
sections carry `[L#]` PubMed citations — offline, across the three subspecialties.
- **det** = deterministic parse (no model) → build_case_dossier (the no-model floor).
- **gt** = full ground-truth context → build_case_dossier (section depth).
- **lit** = Reasoning/Alternatives/Risks carrying `[L#]` via an injected canned PubMed lane
  (no network); fabrication is impossible (only the injected records can be cited). `FAB!`
  would flag any citation outside the injected set.
- **Blind text-judge of section quality + live PubMed recency/relevance: DEFERRED** — no
  provider/NCBI key in CI/this environment (as in WS-1).

- **corpus** = Operative Plan/Surgical Technique/Risks carrying inline `[n]` via an injected
  fake corpus retriever (no corpus in CI); every `[n]` resolves to a retrieved record. `FAB!`
  would flag a citation outside the retrieved set. `[n]` (corpus) stays disjoint from `[L#]`.

| case | subspecialty | det sections | gt sections | gt claims | lit [L#] | corpus [n] |
|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | 8/8 | 8/8 | 32 | 3/3 | 3/3 |
| spine_l4l5_tlif | Spine | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| spine_lumbar_microdisc_l5s1 | Spine | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| spine_thoracic_intradural_meningioma_t6 | Spine | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| skullbase_vs_retrosigmoid | Skull base | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| skullbase_petroclival_meningioma | Skull base | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| skullbase_pituitary_endonasal | Skull base | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| skullbase_cpa_epidermoid | Skull base | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| vascular_mca_clip | Vascular | 8/8 | 8/8 | 32 | 3/3 | 3/3 |
| vascular_acom_clip | Vascular | 8/8 | 8/8 | 32 | 3/3 | 3/3 |
| vascular_pcom_clip | Vascular | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| vascular_avm_resection | Vascular | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| endovascular_acom_coiling | Vascular | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| endovascular_basilar_coiling | Vascular | 8/8 | 8/8 | 32 | 3/3 | 3/3 |
| endovascular_ica_flow_diverter | Vascular | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| endovascular_mca_thrombectomy | Vascular | 8/8 | 8/8 | 32 | 3/3 | 3/3 |
| functional_awake_glioma | Functional | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| functional_dbs_stn_parkinsons | Functional | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| functional_temporal_lobectomy_epilepsy | Functional | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| neurooncology_convexity_meningioma | Neuro-oncology | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| neurooncology_gbm_temporal | Neuro-oncology | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| neurooncology_cerebellar_metastasis | Neuro-oncology | 8/8 | 8/8 | 32 | 3/3 | 3/3 |
| neurooncology_intraventricular_tumor | Neuro-oncology | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| pediatric_cerebellar_pilocytic_astrocytoma | Pediatric | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| pediatric_craniopharyngioma | Pediatric | 8/8 | 8/8 | 31 | 3/3 | 3/3 |
| pediatric_myelomeningocele_closure | Pediatric | 8/8 | 8/8 | 31 | 3/3 | 3/3 |

## Scores
- Deterministic-context all-8-sections: **27/27**
- Full-context all-8-sections: **27/27**
- Literature `[L#]` on all 3 reasoning sections, no fabrication: **27/27**
- Corpus `[n]` on all 3 operative/technique/structures sections, no fabrication: **27/27**

**WS-2/WS-3 acceptance (8 sections render, single evidence axis, `[L#]` separate from `[n]`, zero fabrication, no regressions): MET**.
