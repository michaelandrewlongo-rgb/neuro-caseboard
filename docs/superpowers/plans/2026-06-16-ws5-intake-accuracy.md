# Plan — WS-5: More accurate intake extraction (test-first)

Spec: `docs/superpowers/specs/2026-06-16-ws5-intake-accuracy-design.md`. Strict TDD.

## Tasks

1. **Measure.** Frequency-based laterality on the 27 cases → 0.815 (fixes the 2 symptom-vs-lesion
   bugs); the remaining 5 misses are midline-implicit (no directional token). (Done.)
2. **RED.** `tests/test_intake.py::test_deterministic_laterality_prefers_lesion_over_symptom_side`
   (+ ties / midline guards). Run → fail (first-occurrence picks the symptom side).
3. **GREEN.** `intake.py::_extract_laterality` → most-frequent directional (ties → first occurrence),
   `import collections`. Handedness strip preserved. Run → intake/case_context tests green.
4. **Held-out realism.** State "midline" in the 5 midline-implicit dictations (pituitary, AComA
   coiling, basilar, craniopharyngioma, myelomeningocele) so the floor extracts midline honestly.
5. **Eval.** `intake_eval.py` side 27/27, level 27/27, goal 27/27; bump `eval/BASELINE.json`
   `intake_side_acc` 0.78 → 1.0.
6. **Verify.** Full `pytest` green, 0 regressions; gate green; existing handedness/disc-range tests
   unchanged.
7. **Record.** LOOP_LOG line.

## Non-goals
The keyed live judges (WS-6); any safety/never-event laterality gating.
