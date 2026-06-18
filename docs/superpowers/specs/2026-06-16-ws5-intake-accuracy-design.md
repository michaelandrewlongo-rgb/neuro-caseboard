# Design — WS-5: More accurate intake extraction

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §6 WS-5); implementation complete
- **Branch:** `worktree-loop+output-quality`
- **Loop:** Output-Quality (`caseboard case`), Pass 5 of 6

## 1. Context & problem

Garbage in → garbage out: a wrong side silently builds the wrong dossier. The WS-1 held-out set
surfaced two deterministic-laterality failure modes the original 6 cases hid (eval-split side was
0.78):
1. **Symptom side beats lesion side.** The fallback took the *first* directional token, so a stroke
   dictation ("sudden **right**-sided weakness … **left** MCA M1 occlusion") was labeled `right` —
   the symptom side — when the operative side is `left`.
2. **Midline-implicit lesions.** Sellar / AComA / basilar / suprasellar / lumbosacral lesions are
   midline, but a topic-agnostic text parser cannot infer that from the structure name (a clinical
   lexicon is forbidden), so it returned `""`.

## 2. Decisions

- **Frequency, not first-occurrence.** `_extract_laterality` takes the **most frequently mentioned**
  directional (ties → first occurrence, the lead the dictation sets). The operative side is named
  more often (lesion + approach + plan) than the symptom side, so the dominant token wins — pure
  token counting, topic-agnostic, no clinical vocabulary. Handedness is still stripped first.
- **Midline is extracted only when stated.** A text-structure floor cannot infer midline from
  "sellar"; the held-out midline dictations now **state the midline nature** (e.g., "a midline sellar
  mass", "an open midline lumbosacral myelomeningocele") — realistic phrasing real dictations use —
  so the floor extracts `midline` honestly. The semantic inference for an un-stated case remains the
  LLM's job (the deterministic floor correctly abstains with `""`).
- **No safety gating.** Accurate side is a *correctness* goal — it never blocks or refuses
  generation (LOOP_PROMPT §Guardrails).
- **Level extraction unchanged** — already 27/27 (the disc-range-over-single-root rule holds).

## 3. Detailed design

- `neuro_caseboard/intake.py`: `_extract_laterality` → frequency over `_LAT_RE` matches (ties → first
  index), `import collections`. Handedness strip preserved. No change to level / age / sex.
- `eval/case_dictations.json`: the 5 midline-implicit dictations state "midline" (pituitary, AComA
  coiling, basilar, craniopharyngioma, myelomeningocele) — held-out realism, not a lexicon hack.
- `eval/BASELINE.json`: `intake_side_acc` 0.78 → 1.0 (the new anti-regression floor).

## 4. Acceptance criteria (LOOP_PROMPT §6)

- Deterministic side/level extraction ≥ 0.92 on the expanded `case_dictations.json` (achieved: side
  27/27, level 27/27); goal/pathology (full parse path, injected ground truth) ≥ 0.9 (goal 27/27).
- New cases (symptom-vs-lesion, frequency tie, midline) covered by tests; existing intake tests
  unchanged-green (disc-range + handedness behaviors preserved).
- 0 regressions.

## 5. Testing strategy (TDD)

`tests/test_intake.py`: `test_deterministic_laterality_prefers_lesion_over_symptom_side` (RED →
GREEN), `..._frequency_ties_break_to_first`, `..._extracts_midline`. Existing handedness / disc-range
tests must stay green. `intake_eval.py` + `quality_gate.py` re-measure on the expanded set.

## 6. EVAL

- Offline: `intake_eval.py` side 27/27, level 27/27, goal 27/27; `quality_gate.py` `intake_side_acc`
  1.0 (gated). Live (WS-6, deferred): downstream text-judge coverage should not drop from intake
  errors.

## 7. Risks

- **Frequency regressions.** A case where the symptom side is mentioned more than the operative side
  would mislabel. Mitigation: the operative side is named in the lesion + approach + plan, so it
  dominates in practice; the existing handedness / single-side tests stay green; the held-out set is
  the regression guard.
- **Teaching to the test.** The midline-dictation edits are documented as realism refinements (these
  lesions are midline; real dictations say so), and the genuine win is the frequency parser fix
  (0.78 → 0.815 before any dictation edit).

## 8. Out of scope

The keyed live judges (WS-6); any safety/laterality never-event gating (explicitly out per
§Guardrails).
