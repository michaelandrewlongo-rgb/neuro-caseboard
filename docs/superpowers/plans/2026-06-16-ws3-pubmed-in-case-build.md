# WS-3: PubMed in the case build — Implementation Plan

**Goal:** Reasoning / Alternatives / Risks each carry a synthesized contemporary-literature
paragraph with `[L#]` citations on a separate axis from corpus `[n]`, reusing the existing lane.
Offline tests inject canned PubMed responses; never fabricate.

**Spec:** `docs/superpowers/specs/2026-06-16-ws3-pubmed-in-case-build-design.md`

**Conventions:** `python3 -m pytest` from the worktree root. Branch `worktree-streamlit-executive-navy-loop`.

---

## Task 1: `Section.literature` field (test-first, non-breaking)
- Test (extend `test_compile.py`): `Section` has `literature` defaulting `None`; no confidence axis.
- Impl: add `literature: object | None = None` to `Section` in `model.py`.

## Task 2: `case_literature.py` (test-first)
- Test `tests/test_case_literature.py`: `section_query` (3 sections, topic-agnostic); `attach_case_literature`
  with injected canned cache + synth → 3 target sections get `[L#]`; non-target None; `[L#] ⊆ injected
  PMIDs`; disabled config → none.
- Impl: `section_query`, `attach_case_literature` (reuse `qa.build_literature_section`, injectable).

## Task 3: render literature in markdown (test-first)
- Test (extend `test_render_md.py`): a Section with a literature object renders narrative + `[L#]` rows.
- Impl: extend `render_md.render_markdown`.

## Task 4: wire into `build_case_dossier` (test-first)
- Test (extend `test_pipeline.py`): `build_case_dossier(..., literature=True, lit_cache, lit_synth_client)`
  attaches to the 3 sections offline; `literature=False` none; update the existing offline section test
  to pass `literature=False`.
- Impl: add `literature/lit_client/lit_synth_client/lit_cache` args; call `attach_case_literature`.

## Task 5: EVAL + verify + record
- Extend `eval/case_eval.py`: injected canned lit → report `[L#]` coverage of the 3 sections; assert no
  foreign PMID. Update `eval/CASE_DOSSIER_REPORT`.
- Full suite green; import gate; append Pass-3 line to `LOOP_LOG.md`; commit.
