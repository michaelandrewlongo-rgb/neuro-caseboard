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

| case | subspecialty | det sections | gt sections | gt claims | lit [L#] |
|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | 8/8 | 8/8 | 38 | 3/3 |
| skullbase_vs_retrosigmoid | Skull base | 8/8 | 8/8 | 37 | 3/3 |
| functional_awake_glioma | Functional | 8/8 | 8/8 | 37 | 3/3 |
| vascular_mca_clip | Vascular | 8/8 | 8/8 | 38 | 3/3 |
| neurooncology_convexity_meningioma | Neuro-oncology | 8/8 | 8/8 | 37 | 3/3 |
| pediatric_posterior_fossa_medulloblastoma | Pediatric | 8/8 | 8/8 | 37 | 3/3 |

## Scores
- Deterministic-context all-8-sections: **6/6**
- Full-context all-8-sections: **6/6**
- Literature `[L#]` on all 3 reasoning sections, no fabrication: **6/6**

**WS-2/WS-3 acceptance (8 sections render, single evidence axis, `[L#]` separate from `[n]`, zero fabrication, no regressions): MET**.
