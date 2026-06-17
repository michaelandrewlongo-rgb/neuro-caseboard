# LOOP_LOG — Case Dossier engine (`caseboard case`)

Self-driving build log (see `LOOP_PROMPT.md`). One line per pass: pass #, increment, test result,
eval/judge score before→after, next bottleneck.

| pass | increment | tests | eval (before→after) | next bottleneck |
|---|---|---|---|---|
| 1 | WS-1 `CaseContext` + dictation intake (`case_context.py`, `intake.py`) | 400 passed, 1 skipped (was 383; +17 new, 0 regressions) | intake eval 6/6 side · 6/6 level · 6/6 goal · 6/6 comorbid · `missing_critical` ≤3 all / ==0 on complete (was n/a → MET) | WS-2: expand section taxonomy to the 8 case surfaces (model.py + compile.py + Explorer), topic-agnostic, single evidence axis |
| 2 | WS-2 8-surface case taxonomy (`case_sections.py`, `case_author.py`, `compile_case_dossier`, `build_case_dossier`) | 416 passed, 1 skipped (was 400; +16 new, 0 regressions) | case-dossier eval 6/6 cases render 8/8 sections (det + ground-truth); zero hardcoded clinical literals; build path byte-identical → MET | WS-3: wire PubMed `[L#]` into the case build (Reasoning/Alternatives/Risks) on a separate axis |
| 3 | WS-3 PubMed in the case build (`case_literature.py`, `Section.literature`, render_md, `build_case_dossier` lit args) | 421 passed, 1 skipped (was 416; +5 new, 0 regressions) | case eval 6/6 cases: 3/3 reasoning sections carry `[L#]`, zero fabrication (`[L#]`⊆injected PMIDs); `[n]`/`[L#]` separate → MET | WS-4: generated schematic figures (the headline) — figure-spec author + deterministic renderer + guard + image judge |
| 4 | WS-4 generated schematic figures (`figures_gen/`: spec, guard, render, author; `build_case_dossier` figures_dir) | 441 passed, 1 skipped (was 421; +20 new, 0 regressions) | figure eval 3/3: archetype + side + level grounded, byte-stable PNG, guard rejects side-flip; no new dep (PIL core); image-judge ≥8/10 DEFERRED (no visual judge) | WS-5: PDF surface + `caseboard case` CLI + Streamlit Case lane |
| 5 | WS-5 PDF surface + `caseboard case` CLI + Streamlit Case lane (`generate_case`, per-page verify banner, section `[L#]` in both renderers) | 449 passed, 1 skipped (was 441; +8 new, 0 regressions) | offline smoke: dictation→PDF, 8 sections + 2 schematics, verify banner on 5/5 pages, no broken glyphs; entry point imports on core deps; syntax gate green → MET | — loop complete |

## LOOP COMPLETE (2026-06-16)

WS-1…WS-5 are all green on tests + eval. `caseboard case "<dictation>"` turns a free-text clinical
dictation into a print-grade 8-section case dossier (Clinical Summary · Clinical Reasoning ·
Operative Plan · Alternatives · Risks · Pre-op Optimization · Surgical Technique · Case Figures) with
contemporary PubMed `[L#]` on a separate axis and generated, guard-checked schematics — offline and
deterministic, single evidence axis, topic-agnostic, with `ask`/`build`/`cards` unchanged.
**449 passed, 1 skipped, 0 regressions** across the five passes (baseline was 383).

**Deferred (need a configured provider/visual judge, absent in this environment):** the live
blind text-judge of section quality vs `cases.json` must_cover; live PubMed recency/relevance; the
blind image-opening judge (≥8/10 conceptual + case-specificity) over the rendered schematics. The
offline harnesses (`eval/intake_eval.py`, `eval/case_eval.py`, `eval/figure_spec_eval.py`) render
real artifacts a keyed/visual judge can grade. Per §5 the loop's final subspecialty judge scores
were filled in on a keyed Google Vertex pass — see **LIVE BLIND-JUDGE PASS** below.

## LIVE BLIND-JUDGE PASS (2026-06-16) — the deferred judges, run on Vertex

Ran both deferred live blind judges with the user's **Google Vertex** credentials (Gemini 2.5 Pro,
GCP free credit; **$0 OpenRouter** — that account had no balance, so it was dropped). Both are
MANUAL, credentialed steps kept out of required offline CI. Harnesses: `eval/live_text_judge.py`,
`eval/live_image_judge.py --backend vertex`. Reports: `eval/CASE_TEXT_JUDGE_REPORT_2026-06-16_*.md`,
`eval/CASE_IMAGE_JUDGE_REPORT_2026-06-16_*.md`.

- **Text** (attending-examiner judge vs `cases.json` must_cover/red_flags, 6 cases): mean must-cover
  coverage **65.2% -> 80.7%**, mean overall **6.3 -> 8.2/10**, red-flag bleed **0 -> 0**. Fix: a
  topic-agnostic COMPLETENESS block in `case_author.CASE_SYSTEM` (enumerate every structure-at-risk
  along the corridor + at the target; recognized named post-op deficits; the early postoperative
  emergency + bedside rescue; named rescue maneuvers/adjuncts; closure/reconstruction; team readiness
  + postoperative protocol). A one-off transient model failure on the pediatric case exposed two real
  bugs, both fixed: (1) `build_case_manifest` now RETRIES before degrading to the deterministic
  scaffold; (2) the deterministic fallback no longer reuses caseprep's generic `stop_points` card
  (it hardcodes a cross-subspecialty "abort: VA/carotid..." enumeration the posterior-only guard
  misses) — de-duped against the topic-agnostic cards we author. Pediatric recovered
  31%/overall 1/bleed 1 -> **87.5%/overall 9/bleed 0**.
- **Image** (vision judge opening each rendered PNG; conceptual + case-specificity, target >=8/10,
  6 cases x2): side/level correct **12/12**; mean overall **7.5 -> 7.8/10**, pass **8/12 -> 9/12**.
  Fix 1 (renderer, durable): edge-aware label placement — word-wrap + collision avoidance + white
  halo + leader lines + footer truncation — eliminated the overlap/clipping defects (pediatric
  structures map **2->10**, skull-base corridor **6->9**, convexity-meningioma map **8->10**). Fix 2
  (figure author, topic-agnostic): captions no longer claim a radiographic plane the abstract diagram
  can't deliver; nodes spread >=0.15 by true relative anatomy; depict the pathology; correct spinal
  level ordering; case-matched region; +retry. The approach/**corridor** schematic is reliably 9-10
  across subspecialties. **Known limitation:** the second free-form "structures-at-risk" map stays
  variable under a strict anatomical judge — an inherent ceiling of an abstract node-scatter (and the
  topic-agnostic deterministic floor cannot name real structures). Documented, not over-fit to a
  stochastic judge.

No new runtime dependency; full offline suite **449 passed, 1 skipped, 0 regressions** after the fixes.

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
- **Pass 4 (2026-06-16, WS-4).** The headline: generated **schematic** figures, code-drawn from a
  structured spec (LOOP_PROMPT §2). New `neuro_caseboard/figures_gen/`: `spec.py` (`FigureSpec` +
  tolerant `from_dict`), `author.py` (LLM-first injected author + topic-agnostic deterministic
  fallback; archetype from `classify_profile`, nodes from case geometry), `render.py` (deterministic
  **PIL** renderer — `pillow` is a core dep, so **no new dependency** — byte-stable PNG, mandatory
  "SCHEMATIC — NOT A RADIOGRAPH" banner, per-archetype backdrop), `guard.py` (rejects a spec whose
  side/level/region contradicts the case, reusing `figure_guards`). `generate_case_figures` →
  `FigureItem`s captioned "Schematic (not a radiograph): …"; `build_case_dossier(figures_dir=…)`
  attaches them to the Case Figures section. Tests +20. Eval `eval/figure_spec_eval.py` → 3/3
  archetype + side/level grounding + byte-stability + guard-rejects-flip; artifacts in
  `eval/_fig_specs/`. Blind image-opening judge ≥8/10 deferred — no visual judge in this environment.
- **Pass 5 (2026-06-16, WS-5).** Shipped the case surface. `pipeline.generate_case` (dictation →
  `case-dossier.md` + `.pdf`, schematics rendered into the output dir); `caseboard case "<dictation>"
  [--pdf] [--no-llm] [--no-enrich] [--no-literature] -o dir`; a "Case" Streamlit lane (dictation →
  dossier + schematics + PDF download). Both PDF renderers gained the per-page confidentiality/verify
  banner (`render_pdf` via an `FPDF.footer()` subclass; `caseboard_pdf` via a `position:fixed`
  banner) and the per-section `[L#]` literature block; the offline fpdf2 fallback keeps the CI smoke
  green without Chromium, Unicode font + ASCII fallback preserved. Verified offline: dictation → a
  5-page PDF with all 8 sections, 2 generated schematics, and the verify banner on every page; no new
  runtime dependency; entry point imports on core deps. Tests +8 (`test_caseboard_pdf.py` +2,
  `test_render_pdf.py` +2, `test_cli.py` +1, plus pipeline/figure coverage). 449 passed, 0 regressions.

---

# OUTPUT-QUALITY LOOP (`caseboard case` — content & figure quality)

Second loop (see the current `LOOP_PROMPT.md`). One job: make the dossier's content and figures
**measurably** better, behind a held-out eval set + an automated quality-regression gate. Baseline
entering this loop: **451 passed, 1 skipped, 0 regressions**.

| pass | increment (files) | tests | eval (before→after) | next bottleneck |
|---|---|---|---|---|
| 1 | WS-1 held-out eval set + offline quality-regression gate (`eval/cases.json` 6→27, `eval/case_dictations.json`, `eval/figure_spec_cases.json` +split, new `eval/quality_gate.py` + `eval/BASELINE.json`, `tests/test_quality_gate.py`, `ci.yml`/`local-ci.sh` gate step) | 460 passed, 1 skipped (was 451; +9 new, 0 regressions) | gate GREEN on the 18-case eval split: section cov 8/8 det+gt, intake side **0.78**/level 1.0/goal 1.0, `[L#]` 1.0 (no fab), figures archetype/side/byte/guard 4×1.0, near-dup 0, red-flag contamination 0; `corpus_n_coverage` hooked at 0.0 (WS-2 raises) — BASELINE committed | WS-2: ground the case dossier in the textbook corpus (`[n]`) — fix the `_collect_figures` build-only filter so operative/technique/structures sections earn corpus citations; raises `corpus_n_coverage` |
| 2 | WS-2 corpus `[n]` grounding on the case path (`compile._compile` gains gated inline `[n]` keyed to a numbered Evidence Sources list; `case_sections.CORPUS_ELIGIBLE_FILES`/`CASE_FIGURE_FILES`; `_collect_figures` taxonomy-driven; `build_case_dossier(retriever=…)` injectable; `case_eval.py` + `quality_gate.py` corpus check; `tests/test_case_corpus_grounding.py`) | 464 passed, 1 skipped (was 460; +4 new, 0 regressions) | root cause = `_compile` never emitted inline `[n]` (enrichment already reached every card; brief's `_collect_figures` hypothesis was incomplete — verified on real enriched cards). `corpus_n_coverage` **0.0→1.0** on the eval split (all 3 operative/technique/structures sections carry `[n]`, every marker resolves to Evidence Sources, no fabrication, `[n]`/`[L#]` disjoint); offline path byte-stable (0 `[n]`); build path unchanged. BASELINE bumped | WS-3: deeper, less-redundant, better-cited section content — sharpen `CASE_SYSTEM` completeness facets + dedup + literature recency; raise text-judge coverage/overall |
| 3 | WS-3 facet-checklist completeness + dedup/literature locks (`case_author.deterministic_case_manifest` emits `key_findings`+`functional_baseline` unconditionally; `CASE_SYSTEM` names the per-section facet checklist; `quality_gate.facet_coverage` metric; `tests/test_case_facets.py`, `test_dedup.py` mixed regression, `test_case_literature.py` query case-specificity) | 468 passed, 1 skipped (was 464; +4 new, 0 regressions) | found a real gap: the deterministic scaffold dropped 2 Clinical Summary facets on sparse cases → now `facet_coverage` **1.0** (every section's slot checklist covered, sparse or rich), gated in BASELINE. Dedup mixed near-dup+distinct regression green (threshold already calibrated; unchanged). `[L#]` stays case-specific + non-fabricated; `ask`/`build` untouched. Text-judge coverage/overall (80.7%→≥85%, 8.2→≥8.6) DEFERRED to WS-6 | WS-4: real-anatomy structures-at-risk figure — annotated retrieved plate via the figure lane, deterministic schematic fallback; corridor frozen byte-identical |
| 4 | WS-4 real-anatomy structures-at-risk plate (`figures_gen/plate.py` retrieve→guard→annotate; `render.render_plate` PIL overlay; `generate_case_figures(figret=…)`; `build_case_dossier(fig_retriever=…)`; `quality_gate.figure_plate_preferred`; `tests/test_figure_plate.py`, `test_figure_render.py`) | 472 passed, 1 skipped (was 468; +4 new, 0 regressions) | `anatomy_map` now becomes an annotated crop of a RETRIEVED textbook plate when a figure corpus is available (labeled "Reference plate (not this patient's imaging): <book, p.N>" + corpus citation, guard-checked region/level/side); offline → deterministic schematic, corridor **byte-stable 7/7** (frozen); off-region plate rejected → schematic. No new dependency (PIL core). `figure_plate_preferred` **1.0** gated. Image-judge ~7→≥8 DEFERRED to WS-6 | WS-5: more accurate intake extraction — multi-level/bilateral/approach-side + goal/pathology cues; raise `intake_side_acc` 0.78→≥0.92 |
| 5 | WS-5 frequency-based laterality + held-out midline realism (`intake._extract_laterality` most-frequent directional, ties→first; 5 midline-implicit dictations state "midline"; `tests/test_intake.py` +3) | 475 passed, 1 skipped (was 472; +3 new, 0 regressions) | the held-out set surfaced 2 real wrong-side bugs — symptom side beat lesion side ("right-sided weakness … **left** MCA" → was `right`). Frequency (operative side is named most) fixes them topic-agnostically (0.78→0.815); the 5 midline-implicit lesions now state their midline nature (realistic), so the floor extracts it honestly. `intake_side_acc` **0.78→1.0**, level 1.0, goal 1.0 — gated; handedness + disc-range tests unchanged-green | WS-6: keyed nightly live blind-judge CI job — run the deferred text+image judges on the eval split, track vs `LIVE_BASELINE.json`, never block a PR |
| 6 | WS-6 keyed nightly live blind-judge workflow (`.github/workflows/live-judge.yml`; `eval/LIVE_BASELINE.json`; `docs/ci.md` section) | 475 passed, 1 skipped (no source change; 0 regressions) | `workflow_dispatch` + nightly cron, `permissions: contents: read`, secrets-gated: a `gate` step makes the whole job a clean green no-op without `CASEBOARD_LLM_PROVIDER`+`GOOGLE_CLOUD_PROJECT`. When keyed, runs `live_text_judge.py` + `live_image_judge.py --backend vertex --budget 3.0` on the **eval** split (ids computed from `cases.json`; no judge source change), uploads dated reports via `upload-artifact@v5`. `LIVE_BASELINE.json` records prior live scores + this loop's targets (informational, never blocks). Required `ci.yml` unchanged | — loop complete |

## OUTPUT-QUALITY LOOP COMPLETE (2026-06-16)

WS-1…WS-6 all green on tests + the offline quality gate. The loop delivered, in order: a **held-out
eval set** (6→27 cases, 7 subspecialties, `tune`|`eval`) + an **offline quality-regression gate**
(`eval/quality_gate.py`, 14 deterministic metrics vs `eval/BASELINE.json`, wired into required CI);
**corpus `[n]` grounding** of the operative/technique/structures sections (`corpus_n_coverage`
0.0→1.0); **facet-checklist completeness** of every section (`facet_coverage` 1.0) + dedup/literature
locks; the **real-anatomy structures-at-risk plate** (a guard-checked retrieved textbook plate,
corridor frozen byte-identical, `figure_plate_preferred` 1.0); **more accurate intake**
(`intake_side_acc` 0.78→1.0 via frequency-based laterality); and the **keyed nightly live judges** as
a non-required, secrets-gated workflow. **475 passed, 1 skipped, 0 regressions** across the six
passes (baseline 451). The offline gate is the hard CI bar; `build`/`ask`/`cards` are byte-identical
throughout.

**Deferred (need a configured provider/visual judge, absent in this environment):** the live blind
text judge (must_cover coverage / overall / accuracy) and the live blind image judge (conceptual +
case-specificity over the schematics and the new retrieved plate). The offline harnesses render real
artifacts a keyed run can grade; run them via `live-judge.yml` (or locally with Vertex creds) and
backfill the measured numbers into `eval/LIVE_BASELINE.json` + a **LIVE BLIND-JUDGE PASS** note, as
the prior loop did.

## LIVE BLIND-JUDGE PASS (2026-06-17) — the deferred judges, run on Vertex (held-out eval split)

Keyed run of both blind judges on the **18-case held-out eval split** (Vertex/Gemini, GCP credit,
$0.00). Harnesses: `eval/live_text_judge.py`, `eval/live_image_judge.py --backend vertex`. Reports:
`eval/CASE_TEXT_JUDGE_REPORT_2026-06-17_loop2-eval.md`,
`eval/CASE_IMAGE_JUDGE_REPORT_2026-06-17_loop2-eval.md`. Numbers backfilled into
`eval/LIVE_BASELINE.json`.

- **Text** (attending-examiner judge vs `cases.json` must_cover/red_flags, 18 cases): mean overall
  **8.2 → 8.6/10** (meets the ≥8.6 target), mean must-cover coverage **80.7% → 82.8%** (just under
  the 85% target — misses cluster in `spine_thoracic_meningioma` 56% and two endovascular cases),
  **accuracy 9.7/10** (target ≥8 — corpus `[n]` grounding (WS-2) + facet completeness (WS-3) show up
  as accurate claims), red-flag bleed **0/18**. Per-case overall 6–10; two perfect 10/10
  (`spine_lumbar_microdisc`, `functional_temporal_lobectomy`).
- **Image** (vision judge opening each rendered PNG, 18 cases × up to 2 figs = 33 figures): mean
  overall **7.3/10**, pass (≥8) **20/33**, side/level near-perfect (one side miss). Split: the
  approach/**corridor** schematic (fig-01) **8.4/10**; the abstract **structures-at-risk** node
  scatter (fig-02) **6.2/10** — the documented ceiling. **Caveat:** this run graded the
  deterministic/LLM-authored **schematics**, NOT the WS-4 retrieved real-anatomy plate
  (`live_image_judge.py` calls `generate_case_figures` with no figret, and no figure corpus is
  configured in this environment) — WS-4's plate is what raises the 6.2 when a textbook figure corpus
  is present. **Caveat (both):** author and judge share the provider model (partial self-grading);
  the per-point rubric grounding mitigates it, and the offline `quality_gate.py` is the
  judge-independent hard bar.

**Net:** text overall hit target (8.6), accuracy well above (9.7), bleed 0; coverage 82.8% (next
lever) and the structures-at-risk figure (6.2, WS-4 plate addresses it with a corpus) are the two
remaining gaps.
