# Quality-Regression Gate — WS-1 (2026-06-16)

Reproduce: `python3 eval/quality_gate.py`. Offline + deterministic (no keys/network) on the
held-out **eval** split. Fails CI if any metric regresses below `eval/BASELINE.json`.

| metric | value | baseline | dir | result |
|---|---|---|---|---|
| section_coverage_det | 1.0 | 1.0 | min | PASS |
| section_coverage_gt | 1.0 | 1.0 | min | PASS |
| facet_coverage | 1.0 | 1.0 | min | PASS |
| intake_side_acc | 0.777778 | 0.777778 | min | PASS |
| intake_level_acc | 1.0 | 1.0 | min | PASS |
| intake_goal_acc | 1.0 | 1.0 | min | PASS |
| lit_coverage | 1.0 | 1.0 | min | PASS |
| corpus_n_coverage | 1.0 | 1.0 | min | PASS |
| figure_archetype_acc | 1.0 | 1.0 | min | PASS |
| figure_side_acc | 1.0 | 1.0 | min | PASS |
| figure_byte_stable | 1.0 | 1.0 | min | PASS |
| figure_guard_reject | 1.0 | 1.0 | min | PASS |
| near_dup_rate | 0.0 | 0.0 | max | PASS |
| red_flag_contamination | 0.0 | 0.0 | max | PASS |

**Gate: PASS**
