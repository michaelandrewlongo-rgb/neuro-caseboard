# Generated-Schematic Eval — WS-4 (2026-06-16)

Reproduce: `python3 eval/figure_spec_eval.py`. Ground truth: `eval/figure_spec_cases.json`.
Rendered artifacts: `eval/_fig_specs/<id>-NN.png` (open these for the image judge).

Offline + deterministic: the author proposes specs, the guard drops contradictions, the PIL
renderer is byte-stable. **The blind image-opening judge (>=8/10 conceptual correctness +
case-specificity) is DEFERRED** to a keyed/visual run — no visual judge in this environment.

| case | subspecialty | archetype | arch✓ | side✓ | level✓ | byte-stable | guard-rejects-flip | specs |
|---|---|---|---|---|---|---|---|---|
| spine_acdf_c56 | Spine | spine_level | 1 | 1 | 1 | 1 | 1 | 2 |
| functional_awake_glioma | Functional | corridor | 1 | 1 | 1 | 1 | 1 | 2 |
| vascular_mca_clip | Vascular | vessel_config | 1 | 1 | 1 | 1 | 1 | 2 |

## Scores
- Archetype matches expected: **3/3**
- Side encoded correctly (case-specificity): **3/3**
- Level encoded correctly: **3/3**
- Render byte-stable (same spec → identical PNG): **3/3**
- Guard rejects a side-flipped spec: **3/3**

**WS-4 deterministic acceptance (archetype + side/level grounding, byte-stable renders, contradiction rejected): MET**. Image-judge ≥8/10 deferred.
