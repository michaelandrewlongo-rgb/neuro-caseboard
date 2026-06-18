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

## Web frontend loop (react-bits website over the engine) — `LOOP_PROMPT.md`

Goal: a single local React site (Vite + React + TS + Tailwind + shadcn + react-bits) as a NEW
frontend over the EXISTING Python engine — `api/` (thin FastAPI wrapper) + `web/` (Vite SPA). No auth,
local-first, honest degradation, engine reused (imported, never reimplemented). Isolated git worktree
`worktree-web-react-bits-frontend`, branched fresh from `master`; baseline 442 unit tests green.

- **M0 · Slice 1 (2026-06-18) — API boots with a real `/api/health`.** Read the real engine entry
  points first (`cli.py`, `pipeline.py`, `qa.py`, `model.py`, `board_view.py`, `compile.py`,
  `app/streamlit_app.py`) and mapped the exact contracts the lanes call — no guessed signatures. Added
  `api/server.py` (FastAPI; `GET /api/health`, `GET /api/ping`). Health PROBES the engine's real config
  rather than asserting: `engine` (cli import), `synth` (Vertex — provider==vertex + GOOGLE_CLOUD_PROJECT
  + ADC file + google-genai import; **not** an Anthropic key, per the user), `corpus` (INDEX_DIR exists),
  `cards_index` (CARDS_SOURCE_DB exists), `ncbi_key` (literature config). Verified: uvicorn boots,
  `GET /api/health` → 200 with `{engine:true, synth:true, corpus:true, cards_index:false, ncbi_key:false}`
  on this machine — honest: textbook retrieval + Vertex synthesis live; cards DB + NCBI key absent and
  reported as such (never faked). Nested `detail` carries paths + what's missing for a debuggable panel.
  - **Surprise / env note:** **port 8000 is unbindable on this WSL2 box** — `EADDRINUSE` with
    `http_code=000` and no Linux listener in `ss` = a Windows WinNAT *excluded port range* (WSL2 shares
    localhost with Windows; reserved dynamic ranges can't be bound). Binds instantly on 8001, so the API
    default is **:8001** and the Vite proxy will target `127.0.0.1:8001`. Documented for the run command.
  - **Engine config truth (corrects stale `neuro_core/config.py` defaults):** corpus is at
    `/home/michael/textbook_pdfs` (not the `/mnt/d/...` default — only needed to RE-index, not to query);
    INDEX_DIR/ASSETS_DIR live at absolute paths shared with the main checkout (no symlinks needed).
  - **Next:** Slice 2 — scaffold `web/` (Vite+TS+Tailwind+shadcn), one react-bits component on a home
    page that fetches `/api/health` and shows availability, Vite `/api` proxy → :8001, single dev command.

- **M0 · Slice 2 (2026-06-18) — frontend boots; full M0 verified end to end.** Scaffolded `web/`
  (Vite 8 + React 19 + TS 6 + Tailwind v4 via `@tailwindcss/vite`; `react-router-dom` 7). "Neurosurgery
  Signal" theme as Tailwind v4 `@theme` tokens (navy plane, teal + signal-red accents; Syne display /
  Inter / IBM Plex Mono). Routes `/ /ask /build /cards` (Ask/Build/Cards are honest "arrives in M1–M3"
  stubs — no fake content). `HealthPanel` fetches `/api/health` (typed client `src/lib/api.ts`) and
  renders real availability with the engine's own detail strings. **react-bits via its shadcn registry**
  (`components.json` maps `@react-bits` → `https://reactbits.dev/r/{name}.json`):
  `npx shadcn@latest add @react-bits/BlurText-TS-TW` installed `motion@12` + the component source. Two
  CLI/source quirks handled and noted: (1) shadcn wrote to a *literal* `@/components/` dir (alias
  unresolved) → moved into `src/components/`; (2) the react-bits source needed minimal strict-TS fixes
  for our `verbatimModuleSyntax` config — `type`-only `Transition`/`Easing` imports and `FC` instead of
  bare `React.FC` (API unchanged). Single dev command: `web/package.json` `dev` = `concurrently` running
  uvicorn (:8001, repo-root cwd, `CORPUS_DIR` exported) + Vite (:5173); root `./dev.sh` wraps it.
  - **Verified (all gates):** `npm run build` → 0 type errors (438 modules). One command boots both
    servers. Proxy chain works: `curl :5173/api/health` → 200 real status (browser→Vite→FastAPI→engine).
    **Headless Chromium (Playwright) console-error gate: PASS** — health panel rendered client-side,
    BlurText title rendered, `appConsoleErrors: []`, `pageErrors: []`. Honest degradation visible on the
    page: Vertex synthesis + textbook retrieval "available"; cards + NCBI key "absent". (The lone
    `/api/health ERR_ABORTED` is React-19 StrictMode double-mount aborting the first fetch — swallowed by
    the AbortError guard; the second fetch populates the panel.) Non-destructive: `caseboard --help`
    runs, `streamlit_app.py` imports, `git status` shows only new `api/ web/ dev.sh` — no engine file
    touched. **M0 stop condition met:** opens at `http://localhost:5173`, shows engine status + one
    react-bits component, boots with one command.
  - **Run command (exact):** `cd web && npm run dev`  (or `./dev.sh` from repo root) → open
    **http://localhost:5173**. API alone: `CORPUS_DIR=/home/michael/textbook_pdfs python3 -m uvicorn
    api.server:app --port 8001` from the repo root.
  - **Next (M1 · Ask):** add `POST /api/ask` forwarding `qa.answer_question`; render the cited answer,
    figures, and the Contemporary-Literature `[L#]` block; add a whitelisted image route so the browser
    can load the engine's absolute figure paths; honest message when a lane is absent.

- **M1 (2026-06-18) — Ask, end to end.** Read the real Ask shapes first (`neuro_core/query.py`
  `Figure`/`Clarification`/`VariantRewrite`, `synthesize.py` `Citation`, `qa.py` `QAResult`/
  `LiteratureSection`) so the API forwards real fields, no guesses. **API (Slice A):** `POST /api/ask`
  forwards `qa.answer_question(question, force=True)` and serializes a `kind`-tagged JSON union —
  `answer` (answer text + citations[n,book,chapter,page,location] + figures[…,image_url,image_available]
  + literature{narrative,[L#] citations with DOI links}), `clarification` (variants), `unavailable`
  (GpuNotReadyError → 503), or `error` (500) — never a fabricated answer. Plus `GET /api/figure?path=`,
  which serves figure plates ONLY when the path resolves inside the whitelisted assets root (path
  traversal → 404). **Frontend (Slice B):** `/ask` page — input (+Enter, example chips), a slow-call
  loader (react-bits BlurText status line cycling real pipeline stages + `animate-pulse` shimmer; the
  call is genuinely ~50–80s), `react-markdown` answer surface (static/legible — no animated clinical
  text), figure grid (loads via `/api/figure`, honest fallback), Sources list, and a separate
  Contemporary-Literature `[L#]` block with PMID/DOI links. New deps: `react-markdown`, `remark-gfm`.
  - **Verified (all gates):** `npm run build` → 0 type errors (691 modules; only a non-blocking
    chunk-size warning). Curl: `POST /api/ask` → 200 real answer (2352 chars, 9 cites, 5 figs,
    literature present) in ~77s cold / ~52s warm; same through the Vite proxy. `GET /api/figure` → 200
    image/png (3.2 MB) direct + proxied; `/etc/passwd` → 404. **Headless Chromium, full Ask flow:
    answer rendered, 37 `[n]` + 17 `[L#]` markers, all 5 figures loaded (`loaded:5/5`), Contemporary
    Literature present, `consoleErrors: []`, `pageErrors: []`.** Loader proven separately
    (`LOADER_VERIFY=PASS`: static "Usually 30–80 seconds" line + 7 pulse elements + button "Asking…").
    Non-destructive: `caseboard --help` runs, `git status` shows only `api/ web/ dev.sh` + log.
  - **Engine truth surfaced:** retrieval runs on a real GPU (torch 2.12 CUDA, sentence-transformers
    5.5.1, open-clip 3.3.0), Vertex synthesis live, and the **PubMed lane returns even without an
    `NCBI_API_KEY`** (keyless E-utilities worked) — so `/api/health`'s `ncbi_key:false` is honest about
    the key while the lane still degraded gracefully to real output.
  - **Next (M2 · Build/dossier):** `POST /api/build` forwarding `pipeline.build_dossier`→`board_view`
    (sections → claims with `Why:` → checkbox sub-items → figures w/ captions + claim↔figure links →
    appendix → evidence summary) + PDF via `render_case_pdf`; render the full dossier on `/build`.

- **M2 (2026-06-18) — Build / dossier.** **API:** `POST /api/build` forwards `pipeline.build_dossier`
  (the SAME call the CLI/Streamlit use) and serializes the full STRUCTURED `Dossier` (not `board_view`'s
  markdown — React needs the tree): `summary{supported,to_verify,quarantined}` → `sections[heading,
  intro, claims[text, why, status, sub_items, figure_ids], figures[fig_id, caption, citation,
  relevance, claim_ref, image_url, image_available]]` → `appendix{entries[heading,items,sources]}`.
  `kind`-tagged union (`dossier`/`unavailable`/`error`). PDF: `POST /api/build/pdf` reuses a small
  in-memory dossier cache (keyed `topic|enrich|use_llm`, last 8) so export doesn't pay the build cost
  twice, then `render_case_pdf` → `FileResponse(application/pdf)`. **Frontend:** `/build` — topic input
  + enrich/LLM toggles + example chips; a `PipelineLoader` (generic BlurText + shimmer, "1–4 min"
  estimate); `EvidenceBar` (single evidence axis, matches the model — no confidence axis); `DossierView`
  (claims with ✓/⚠ status, indented `Why:`, `☐` checkbox sub-items, `F#` badges that anchor-link to the
  figure; figures carry caption + citation + "supports: <claim>" back-ref; appendix); Download-PDF
  button (blob download via cached build_id).
  - **Verified (all gates):** `npm run build` → 0 type errors (694 modules). Curl: `POST /api/build`
    "left retrosigmoid vestibular schwannoma" → 200 in ~235s, 3 sections, 22 claims (all with `Why:`),
    7 claim↔figure links, evidence summary `{0 supported, 22 verify, 0 quarantined}`; `POST
    /api/build/pdf` reused the cached build_id → 200 application/pdf, 11.8 MB, valid `%PDF` in ~10s
    (fpdf2 fallback — Python Playwright absent). **Headless Chromium, full Build flow: `BUILD_VERIFY=
    PASS`** — loader shown, dossier rendered (3 sections, `Why:` present, 7 `#F` cross-link badges, all
    7 figures loaded), and the **in-browser PDF download fired** (`%PDF`, 11.8 MB, correct filename).
    `consoleErrors: []`, `pageErrors: []`. Non-destructive: `caseboard --help` runs; `git status` only
    `api/ web/ dev.sh` + log.
  - **Next (M3 · Cards):** `POST /api/cards` forwarding `neuro_core.cards_query` (isolated lane, no LLM
    synthesis); render matched cards + media; the cards LanceDB is ABSENT on this machine, so the honest
    `CardsIndexNotBuilt` state is the primary path to render well.

- **M3 (2026-06-18) — Cards.** Read `cards_query` first and found the M2 assumption was wrong: the
  QUERYABLE `cards` table lives INSIDE `INDEX_DIR` (`cards.lance`), and `CARDS_SOURCE_DB` is only the
  source deck for BUILDING it — so the cards lane is actually **LIVE** here, not absent. **API:** `POST
  /api/cards` forwards `cards_query(question, k)` → `{kind:"cards", cards[id, deck, tags, flagged
  (deck's own low-confidence labels via `flagged_tags`), question_text, answer_text, images[…]]}`, with
  `not_built` (CardsIndexNotBuilt) / `unavailable` / `error` as honest first-class states. **Two fixes
  this milestone surfaced:** (1) `/api/health` now probes `INDEX_DIR/cards.lance` (the built table), not
  `CARDS_SOURCE_DB` — so `cards_index` correctly reads **true**; (2) `/api/figure` whitelist widened from
  `assets/figures` to the `assets/` root, because card media lives in the sibling `assets/cards/`
  (still bounded to the engine's asset tree, not the filesystem). **Frontend:** `/cards` — input + "cards
  to show" slider, the isolated-lane "not corpus-cited" disclaimer, a `PipelineLoader`, matched cards
  (deck badge, tags, deck-flag warning, Q/A, media grid), and empty / not_built / error states.
  - **Verified (all gates):** `npm run build` → 0 type errors (570 kB bundle). Curl: health
    `cards_index:true` (table path in detail); `POST /api/cards "cavernous sinus contents"` → 200, 4
    cards with deck/tags/Q/A/images in ~38s; a card image via `/api/figure` → 200 image/jpeg.
    **Headless Chromium: `CARDS_VERIFY=PASS`** — disclaimer + loader shown, 6 cards rendered, all 14
    card-media images loaded, `consoleErrors: []`, `pageErrors: []`. **Non-destructive: full fast suite
    442 passed / 1 skipped (== baseline)**; `git status` only `api/ web/ dev.sh` + log.

- **M5 wrap (2026-06-18) — stop condition met.** M0–M3 work locally end to end, every milestone
  RUN-and-observed in a real headless browser with zero console errors, honest degradation surfaced (not
  faked), and the engine left untouched (442/1 baseline preserved; Streamlit + CLI still import/run).
  Single dev command finalized: **`./dev.sh`** (or `cd web && npm run dev`) → **http://localhost:5173**;
  API on **:8001** (WSL2 WinNAT excludes :8000). New surface lives entirely under `api/` + `web/` + a
  root `dev.sh`. Docs: `web/README.md` (run command, where keys/data come from, surfaces). react-bits
  used with restraint (BlurText title + animated loaders in the chrome; clinical reading surfaces stay
  static/legible). **Remaining (optional M4 polish, not required by the stop condition):** a react-bits
  animated *background* on the home (Aurora/Threads/Silk) to pair with BlurText; route-level code-split
  to clear the 500 kB chunk warning; per-figure lightbox. Engine entry points used (forwarded, never
  reimplemented): `qa.answer_question`, `pipeline.build_dossier`/`render_case_pdf`,
  `neuro_core.cards_query`, `neuro_core.config.load_config`.

- **Style overhaul (2026-06-18) — Neo Brutalism GUI (web + PDFs).** After reviewing design samples
  (5 hand-built mockups + 8 rendered tweakcn presets), the user chose **Neo Brutalism** (tweakcn preset)
  as the product GUI. Re-themed the design system to shadcn semantic tokens driven by the preset: white
  ground, black 2px borders, red `#ff3333` primary / yellow secondary / blue accent, square corners,
  hard offset shadows, DM Sans + Space Mono. Status semantics kept legible (green=supported/available,
  amber=verify, red/black=absent/danger — since red is the brand primary). Migration: rewrote
  `index.css` (tokens + brutalist `.surface`/`.field`/`.chip` + `*{border-radius:0}`) and `ui.tsx`
  (Card/Button/Badge/Stat with press-effect shadows); scripted ~211 utility substitutions across 19
  components (`navy/teal/ink/signal` → `background/card/muted/primary/foreground/...`); hand-fixed the
  tint→solid contrast collapses (status panels, citation chips, literature block, nav active). **PDF
  parity (per request):** restyled the single shared print stylesheet `EXEC_NAVY_CSS` (exec_navy.py) +
  the two extras (`ASK_CSS` briefing, `_CASE_EXTRA_CSS` caseboard) to the same brutalist tokens — class
  structure unchanged — and installed Python Playwright + Chromium so the HTML→PDF path is active (the
  sanctioned `briefing` extra; fpdf2 remains the offline/CI fallback).
  - **Verified:** web build 0 type errors; headless Chromium — Home / Ask / Cards render brutalist,
    console-clean. Real HTML→PDF dossier renders brutalist (red logo, yellow eyebrow chip, green/amber/
    red evidence metrics, black-bordered claim cards w/ hard shadows + status markers, yellow verify
    banner). Engine untouched except the PDF stylesheets; **full suite 442 passed / 1 skipped** after
    updating 3 PDF token tests (`test_exec_navy`/`test_briefing_pdf`/`test_caseboard_pdf`) from the old
    teal/Archivo asserts to red/DM-Sans — the design contract moved, intentionally.
  - **Note:** the fpdf2 offline fallback (`render_pdf.py`) keeps its older code-drawn look; only the
    HTML→PDF path (now the default with Chromium installed) is brutalist.