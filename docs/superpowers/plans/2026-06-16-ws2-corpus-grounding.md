# Plan — WS-2: Ground the case dossier in the corpus (`[n]`) (test-first)

Spec: `docs/superpowers/specs/2026-06-16-ws2-corpus-grounding-design.md`. Strict TDD.

## Tasks

1. **Reproduce (Phase 2).** With a fake corpus retriever, inspect the *real* enriched cards +
   compiled dossier: enrichment reaches every card (`papers=3`) but `_compile` emits 0 inline `[n]`
   → the owning layer is `_compile`, not `_collect_figures`. (Done — recorded in the spec.)
2. **RED.** `tests/test_case_corpus_grounding.py`: claims on Operative Plan / Surgical Technique /
   Risks carry `[n]`; `[n]` resolve to Evidence Sources (no fabrication); offline path has 0 `[n]`;
   `[n]`/`[L#]` disjoint. Run → fail (`build_case_dossier` has no `retriever=`; no inline `[n]`).
3. **GREEN.**
   - `case_sections.py`: `CORPUS_ELIGIBLE_FILES` (04/05/08), `CASE_FIGURE_FILES` (+09).
   - `compile._compile(corpus_inline, corpus_eligible)`: inline `[n]` on eligible-section claims with
     `.papers`, keyed to a numbered Evidence Sources list; `compile_case_dossier` turns it on; build
     path defaults off (byte-identical).
   - `pipeline.build_case_dossier(retriever=…)` injectable; `_collect_figures(eligible_files=…)`
     taxonomy-driven (build keeps `03-anatomy-at-risk.md`).
   - Run tests → green; build-path compile/render goldens stay green.
4. **Fold into eval.** `case_eval.py` + `eval/quality_gate.py` build a corpus-grounded dossier
   (injected fake corpus, figures off) and assert `[n]` on the 3 sections; bump
   `eval/BASELINE.json` `corpus_n_coverage` 0.0→1.0.
5. **Verify (Phase 7).** Full `pytest` green, 0 regressions; gate green; corpus `[n]` proven ACTIVE
   (0.0→1.0) while the offline path stays at 0 `[n]`; `caseboard` imports.
6. **Record.** LOOP_LOG line + this narrative.

## Non-goals
The real-anatomy plate (WS-4); section depth (WS-3); intake accuracy (WS-5).
