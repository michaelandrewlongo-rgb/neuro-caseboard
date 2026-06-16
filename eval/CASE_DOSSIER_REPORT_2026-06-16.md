# Case Dossier Section-Coverage Eval — WS-2 (2026-06-16)

Reproduce: `python3 eval/case_eval.py`. Ground truth: `eval/case_dictations.json`.

Checks all eight LOOP_PROMPT §0 surfaces render, offline, across the three subspecialties.
- **det** = deterministic parse (no model) → build_case_dossier (the no-model floor).
- **gt** = full ground-truth context → build_case_dossier (section depth).
- **Blind text-judge of section quality vs cases.json must_cover: DEFERRED** — no provider
  key in CI/this environment (as in WS-1).

| case | subspecialty | det sections | gt sections | gt claims |
|---|---|---|---|---|
| spine_acdf_c56 | Spine | 8/8 | 8/8 | 38 |
| skullbase_vs_retrosigmoid | Skull base | 8/8 | 8/8 | 37 |
| functional_awake_glioma | Functional | 8/8 | 8/8 | 37 |
| vascular_mca_clip | Vascular | 8/8 | 8/8 | 38 |
| neurooncology_convexity_meningioma | Neuro-oncology | 8/8 | 8/8 | 37 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric | 8/8 | 8/8 | 37 |

## Scores
- Deterministic-context all-8-sections: **6/6**
- Full-context all-8-sections: **6/6**

**WS-2 acceptance (8 sections render, single evidence axis, no regressions): MET**.
