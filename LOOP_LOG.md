# LOOP_LOG — Case Dossier engine (`caseboard case`)

Self-driving build log (see `LOOP_PROMPT.md`). One line per pass: pass #, increment, test result,
eval/judge score before→after, next bottleneck.

| pass | increment | tests | eval (before→after) | next bottleneck |
|---|---|---|---|---|
| 1 | WS-1 `CaseContext` + dictation intake (`case_context.py`, `intake.py`) | 400 passed, 1 skipped (was 383; +17 new, 0 regressions) | intake eval 6/6 side · 6/6 level · 6/6 goal · 6/6 comorbid · `missing_critical` ≤3 all / ==0 on complete (was n/a → MET) | WS-2: expand section taxonomy to the 8 case surfaces (model.py + compile.py + Explorer), topic-agnostic, single evidence axis |
| 2 | WS-2 8-surface case taxonomy (`case_sections.py`, `case_author.py`, `compile_case_dossier`, `build_case_dossier`) | 416 passed, 1 skipped (was 400; +16 new, 0 regressions) | case-dossier eval 6/6 cases render 8/8 sections (det + ground-truth); zero hardcoded clinical literals; build path byte-identical → MET | WS-3: wire PubMed `[L#]` into the case build (Reasoning/Alternatives/Risks) on a separate axis |
| 3 | WS-3 PubMed in the case build (`case_literature.py`, `Section.literature`, render_md, `build_case_dossier` lit args) | 421 passed, 1 skipped (was 416; +5 new, 0 regressions) | case eval 6/6 cases: 3/3 reasoning sections carry `[L#]`, zero fabrication (`[L#]`⊆injected PMIDs); `[n]`/`[L#]` separate → MET | WS-4: generated schematic figures (the headline) — figure-spec author + deterministic renderer + guard + image judge |

## Notes

- **Pass 1 (2026-06-16, WS-1).** Built the structured intake foundation: `CaseContext` dataclass
  (geometry/history/plan + `to_topic()` bridge to the existing pipeline, `missing_critical()` capped
  at 3) and an LLM-first `intake.parse_dictation` (injected `complete_fn`, graceful fallback) with a
  topic-agnostic `deterministic_parse` (age/sex/laterality/level — handedness-aware, disc-range
  preferred over single root level). Offline tests (`test_case_context.py` ×6, `test_intake.py` ×11)
  + a reproducible offline eval (`eval/case_dictations.json`, `eval/intake_eval.py` →
  `eval/CASE_INTAKE_REPORT_2026-06-16.md`). Two bugs the eval caught and fixed in-loop: handedness
  ("right-handed") polluting lesion laterality; single root level ("C6") winning over the disc range
  ("C5-6"). Live model-quality blind grade deferred — no provider key in this environment.
  No new runtime dependency; `caseboard` entry point still imports on core deps.
- **Pass 2 (2026-06-16, WS-2).** Added the eight-surface case taxonomy and an additive case path
  (build untouched): `case_sections.py` (the 8 §0 surfaces with generalizable slot vocab; Operative
  Plan + Risks reuse the build files verbatim), a `compile_case_dossier` built by extracting a
  parameterized `_compile` core from `compile_dossier` (behavior-preserving), a `case_author.py`
  (LLM-first injected author + grounded topic-agnostic deterministic scaffold covering all 8
  sections), and `pipeline.build_case_dossier` (anti-bleed guard → enrich → audit → compile_case).
  Tests: `test_case_sections.py` ×4, `test_case_author.py` ×8, `test_compile.py` +1, `test_pipeline.py`
  +1 (parametrized ×3). Eval `eval/case_eval.py` → `eval/CASE_DOSSIER_REPORT_2026-06-16.md`: 6/6 cases
  render 8/8 sections (deterministic + ground-truth context). Guardrails verified: no hardcoded
  clinical literals in source (grep), build path byte-identical, single evidence axis preserved. Live
  blind text-judge of section quality deferred — no provider key.
- **Pass 3 (2026-06-16, WS-3).** Wired the existing PubMed lane into the case build on a separate
  `[L#]` axis: `Section.literature` (duck-typed, optional — model stays decoupled);
  `case_literature.attach_case_literature` calls `qa.build_literature_section` once per
  reasoning-bearing section (Clinical Reasoning / Alternatives / Risks) with a topic-agnostic
  case-tuned query; `render_md` renders the narrative + `[L#]` rows; `build_case_dossier` gains
  `literature`/`lit_client`/`lit_synth_client`/`lit_cache` args (None → `LITERATURE_RETRIEVAL`).
  Never fabricates — synth cites only the records it is given, citations enumerate those records, and
  tests assert `[L#] ⊆ injected PMIDs`. Offline tests inject a canned cache + synth (no network):
  `test_case_literature.py` ×3, `test_render_md.py` +1, `test_pipeline.py` +1. Eval `case_eval.py`
  extended: 6/6 cases carry `[L#]` on all three sections, no fabrication. Live PubMed recency/relevance
  grade deferred — no `NCBI_API_KEY`. `ask` literature path unchanged.
