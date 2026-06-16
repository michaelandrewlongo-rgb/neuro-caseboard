# Plan — WS-4: Real-anatomy structures-at-risk figure (test-first)

Spec: `docs/superpowers/specs/2026-06-16-ws4-retrieved-plate-design.md`. Strict TDD.

## Tasks

1. **RED.** `tests/test_figure_plate.py`: fake figret + a real PNG → `anatomy_map` becomes a
   reference plate (caption + citation, valid PNG); a contradicting (off-region) plate is rejected →
   schematic; no figret → deterministic schematic. Run → fail (no `figret` kwarg).
2. **GREEN.**
   - `figures_gen/render.py`: `render_plate` (PIL overlay: reference banner + citation; deterministic;
     `render_spec` untouched).
   - `figures_gen/plate.py`: `build_plate_figure` (retrieve → guard via `guard_spec` → annotate →
     reference-plate `FigureItem`; `None` when no figret/record/file or guard-rejected).
   - `figures_gen/__init__.py`: `generate_case_figures(figret=…)` — `anatomy_map`+figret → plate else
     schematic; corridor/other specs unchanged.
   - `pipeline.build_case_dossier(fig_retriever=…)` → resolves `build_figure_retriever()` (None
     offline) and passes it down.
   - Force the deterministic author in the tests (`CASEBOARD_LLM=0`). Run → green.
3. **Render lock.** `tests/test_figure_render.py`: `render_plate` writes a valid, deterministic PNG.
4. **Gate.** `eval/quality_gate.py` `figure_plate_preferred` (plate used with a fake figret; schematic
   offline) → 1.0; bump `eval/BASELINE.json`.
5. **Verify.** Full `pytest` green, 0 regressions; corridor byte-stability (`figure_spec_eval`) 7/7;
   no new dependency.
6. **Record.** LOOP_LOG line.

## Non-goals
Intake (WS-5); the keyed live image judge (WS-6); touching the corridor schematic; a semantic
structure-label layer beyond the plate caption.
