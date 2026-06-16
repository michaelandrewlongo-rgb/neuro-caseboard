# Quality-Regression Gate — WS-1 (2026-06-16)

Reproduce: `python3 eval/quality_gate.py`. Offline + deterministic (no keys/network) on the
held-out **eval** split. Fails CI if any metric regresses below `eval/BASELINE.json`.

| metric | value | baseline | dir | result |
|---|---|---|---|---|
| section_coverage_gt | 1.0 | 2.0 | min | FAIL |

**Gate: FAIL**
