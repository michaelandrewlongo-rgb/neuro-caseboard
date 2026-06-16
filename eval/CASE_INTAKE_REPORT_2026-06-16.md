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
| skullbase_vs_retrosigmoid | Skull base | left OK | - OK | OK | OK | 3 | OK |
| functional_awake_glioma | Functional | left OK | - OK | OK | OK | 3 | OK |
| vascular_mca_clip | Vascular | left OK | - OK | OK | OK | 3 | OK |
| neurooncology_convexity_meningioma | Neuro-oncology | right OK | - OK | OK | OK | 3 | OK |
| pediatric_posterior_fossa_medulloblastoma | Pediatric | midline OK | - OK | OK | OK | 3 | OK |

## Scores
- Deterministic side: **6/6**
- Deterministic level: **6/6**
- Goal captured (parse path): **6/6**
- Comorbidities captured (parse path): **6/6**
- `missing_critical()==0` on complete record: **6/6**
- `missing_critical()<=3` on deterministic parse: **6/6**

**WS-1 acceptance: MET** (side/level extracted, goal+comorbidities captured, missing_critical conservative).
