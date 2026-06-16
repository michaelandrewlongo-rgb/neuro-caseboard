# WS-2: Expanded section taxonomy (8 case surfaces) — Implementation Plan

**Goal:** Add the 8-surface case taxonomy + a case-section author + a `compile_case_dossier` /
`build_case_dossier` path, additive and topic-agnostic, with `build`/`ask` unchanged. Offline tests.

**Spec:** `docs/superpowers/specs/2026-06-16-ws2-case-section-taxonomy-design.md`

**Conventions:** `python3 -m pytest` from the worktree root. Branch `worktree-streamlit-executive-navy-loop`.

---

## Task 1: `case_sections.py` taxonomy (test-first)
- Test `tests/test_case_sections.py`: 8 sections present & ordered; reused files (04/05) equal the
  build files; slot-label Title-Casing.
- Impl `neuro_caseboard/case_sections.py`.

## Task 2: `compile_case_dossier` (test-first, non-breaking)
- Extract pure `_compile(...)` from `compile_dossier`; keep `compile_dossier` behavior-identical.
- Add `compile_case_dossier(audited, *, case, ...)` using CASE headings/order/intros.
- Test: extend `tests/test_compile.py` — 8 headings render in order on a fake audited case manifest;
  existing compile_dossier tests stay green.

## Task 3: `case_author.py` (test-first)
- `build_case_manifest` (injected `complete_fn`) + `deterministic_case_manifest` +
  `_coerce_case_cards`. Reuse `pipeline._deterministic_manifest` for the 04/05 cards; scaffold the
  5 new sections from `case` fields + `ontology.required_dimensions`.
- Test `tests/test_case_author.py` (mirror `test_explore_llm.py`): injected fake across 8 files,
  invalid dropped; deterministic ≥1 card per section for spine/cranial/vascular; no-clinical-literal
  guard.

## Task 4: `build_case_dossier` pipeline seam (test-first)
- Add `build_case_dossier(case, *, enrich=True, use_llm=None)` to `pipeline.py`; keep
  `guard.prune_offtarget` in the path.
- Test: extend `tests/test_pipeline.py` — injected author fake, `enrich=False` → 8-section Dossier;
  `build_dossier` regression unchanged.

## Task 5: EVAL + verify + record
- `eval/case_eval.py` over `eval/case_dictations.json` → assert 8 sections per case across 3
  subspecialties; write `eval/CASE_DOSSIER_REPORT_2026-06-16.md`.
- Full suite green; import gate; append Pass-2 line to `LOOP_LOG.md`.
