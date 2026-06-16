# WS-4: Generated schematic figures — Implementation Plan

**Goal:** LLM-authored structured figure specs + a deterministic PIL renderer (byte-stable PNG, no
new dep) + an anti-bleed guard, attached as schematic `FigureItem`s. Offline tests.

**Spec:** `docs/superpowers/specs/2026-06-16-ws4-generated-schematic-figures-design.md`

**Conventions:** `python3 -m pytest` from the worktree root. Branch `worktree-streamlit-executive-navy-loop`.

---

## Task 1: `figures_gen/spec.py` (test-first)
`FigureSpec`/`FigureNode`/`FigureEdge` + tolerant `from_dict` (clamp x/y, drop bad nodes). Test
`tests/test_figure_spec.py`.

## Task 2: `figures_gen/guard.py` (test-first)
`guard_spec(spec, case)` (side/level/region contradiction) + `filter_specs`. Reuse
`figure_guards._levels_in` / `figure_offtarget`. Test `tests/test_figure_guard.py`.

## Task 3: `figures_gen/render.py` (test-first)
`render_spec(spec) -> PNG bytes` (PIL, bundled DejaVu, mandatory schematic banner, per-archetype
layout). Byte-stable. Test `tests/test_figure_render.py` (PNG header, byte-identical, all archetypes).

## Task 4: `figures_gen/author.py` (test-first)
`build_figure_specs` (LLM-first, injected) + `deterministic_figure_specs` (archetype by profile,
case-aligned geometry). Test `tests/test_figure_author.py`.

## Task 5: `figures_gen/__init__.py` + pipeline integration (test-first)
`generate_case_figures(case, out_dir, ...)` -> FigureItems (schematic caption). `build_case_dossier
(..., figures_dir=)` attaches them to the Case Figures section. Tests `tests/test_case_figures.py`,
`tests/test_pipeline.py` (+1).

## Task 6: EVAL + verify + record
`eval/figure_spec_cases.json` + `eval/figure_spec_eval.py` -> `eval/FIGURE_SPEC_REPORT_2026-06-16.md`
(byte-stability + guard + side/level present; live image judge deferred). Full suite green; import
gate; append Pass-4 line to `LOOP_LOG.md`; commit.
