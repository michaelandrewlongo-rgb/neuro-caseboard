# EXPERIMENT_BACKLOG — Neuro·Caseboard Ask pathway

Prioritized, independently-actionable tasks for the **Ask** pathway, judged against
`CLEAN_ROOM_BASELINE.md`. Each is sized to the **smallest coherent change**. Priority column =
charter ladder (1=data-integrity … 10=cosmetic). "Shared" = touches code also used by the
out-of-scope Dossier/Cards/briefing surfaces → **must include a regression check** those still pass.

Evidence was source-verified (the items marked ✓me I read personally; the rest are workflow-agent
findings with current file:line evidence, to be re-confirmed at implementation time). The map's
"by design / fail-open" framing is **stripped** — each behavior is judged on its merits.

Legend: **DO** = planned this run · **CAL** = needs benchmark calibration / paid grading (likely
human) · **LOW** = low value/latent, deferred.

---

## Tier 1 — data integrity (priority 1); small, safe, no calibration

- **B1 ✓me · DO · A1 — Dangling/invented citation markers are counted *supported*.**
  `verify_answer` (`answer_verify.py:87`) builds the premise via `premises.get(m)`; a marker whose
  key is absent (an invented `[7]`/`[L5]` beyond the real sources) → empty premise →
  `should_cite` abstains→keep (`entailment.py:113-114`) → claim `supported=True`, never in
  `unsupported_markers`, groundedness stays 1.0. Keys are exactly the real source set
  (`qa.py:201-204,254-258`, `qa_stream.py:143-146`). **Fix:** in `verify_answer`, partition markers
  into resolvable (key ∈ premises) vs dangling; a claim with any dangling marker is unsupported and
  its dangling markers surface (honest wording: "references a source not in the list", distinct from
  "not entailed"). **Shared:** `verify_answer` is Ask-only, but reused by briefing bundle — keep
  `should_cite` untouched; regression-check briefing tests. Update the mis-named
  `test_missing_premise_is_non_destructive` (it pins the wrong behavior; flag for clinician review).

- **B2 ✓me · DO · A1/A10 — Dangling `[L#]` chips in the DEFAULT woven path.** Default
  `weave=True` returns `LiteratureSection(narrative="", citations=[…])`
  (`qa.py:194-199`, `qa_stream.py:133-140`), but `LiteratureBlock.tsx:23` `if (!literature.narrative)
  return null` drops the whole PubMed `<ol>` of `src-literature-N` anchors → inline `[L#]` chips
  resolve to nothing. **Fix:** render the citations `<ol>` whenever `citations.length>0`; only the
  narrative `<ReactMarkdown>` stays conditional on `narrative`. **Ask-only** (LiteratureBlock
  imported only by Ask.tsx). vitest guard.

- **B10 · DO · A5 — Separate-lane: literature block attached onto a textbook REFUSAL.** In the
  non-default injected separate path, `answer_question` attaches the `[L#]` block even when Lane A
  is a refusal (`qa.py:256-265`). **Fix:** when `is_refusal(qr.answer)`, set `literature=None`
  (mirror the woven path `qa.py:185-187`). Tiny, Ask-only.

- **B13 · DO · A6 — `/api/ask/start` empty-question 422 omits `kind`.** `server.py:440` returns
  `{"error":...}` while `/api/ask` returns `{"kind":"error","error":...}` (`server.py:477`); the SPA
  discriminates on `kind`. **Fix:** return `{"kind":"error","error":"empty question"}`. Tiny,
  Ask-only.

---

## Tier 2 — correctness · transparency · reliability (priority 1–3); high value

- **B3 ✓me · DO · A2/A6/§4 — Verifier verdict is invisible on the primary (web) surface.**
  `verify_answer` output is computed + serialized (`api/server.py:408-410,510`) + stored
  (`askStore.ts:71`) but **no Ask UI reads `state.verification`** — flagged (unsupported / dangling)
  markers render identically to supported ones. The CLI shows it (`cli.py:49-53`); the web silently
  bypasses it. **Fix:** in `Ask.tsx` ResultView, when `verification.n_unsupported>0` (or dangling
  markers exist) render a visible needs-verification banner listing the markers; don't mutate the
  answer string. **Ask-only**, additive store read. vitest guard. (Subsumes much of B4.)

- **B12 ✓me · DO · A6 — `startAsk` ignores `res.ok`/`job_id` → silent stuck loader.**
  (`api.ts:132-137`) a 422/5xx body yields `job_id=undefined` → stream to `/stream/undefined`.
  **Fix:** throw on `!res.ok`/missing `job_id`; `run()` surfaces the existing netError card.
  Ask-only.

- **B11 · DO · A6 — Reconnect to an evicted/expired job (LRU cap 8) hangs forever.**
  `server.py:454` returns 404; `Ask.tsx:71` `onError:()=>{}` no-ops and status stays `streaming`.
  **Fix:** on EventSource error without a terminal `done`, set a visible terminal error/`netError`
  state and re-enable the form. Ask-only.

- **B5 · DO · A3 — No numeric backstop (doses/thresholds/percentages).** The tokenizer drops
  tokens `<3` chars (`entailment.py:40-41`), so `20` (mg), `30` (%), `5` (mm) are invisible; the
  Lexical/bleed checks never compare numbers. A fabricated dose passes if surrounding words overlap.
  **Fix:** in `verify_answer`, extract numeric+unit/percent spans from the de-markered claim; flag
  the claim needs-verification when a claim numeric is absent from its cited premise (parallel to
  the bleed guard). **Shared** (entailment helpers reused by briefing) — keep the check in
  `verify_answer`; regression-check briefing. Safety-critical (Persona C, baseline §10 case 5) →
  flag for clinician review.

- **B17 · DO · A3/A7 — Figure-cited claims bypass entailment.** Appended figure citations have
  empty `.text` (`synthesize.py:97-99`), so `premises[figure_n]==""` → abstain→keep; a claim cited
  to a figure is never checked, though `f.caption` exists. **Fix:** thread the caption into the
  premise for figure sources (still abstain on genuinely empty captions). **Shared-ish**: Ask-only
  (build_citations); regression-check.

- **B6 · DO · A2 — Uncited clinical sentences are auto-`supported`.** `answer_verify.py:83-84`.
  **Fix:** when an uncited sentence contains a `medical_entity` (or numeric), flag it
  needs-verification instead of `supported=True`. **Shared** (verify_answer used by briefing) — guard
  with the `medical_entities` low-FP heuristic; regression-check briefing for over-flagging.

- **B8 · DO · A12/A6 — Disambiguation analyzer fail-open is silent.** `query_analyze.py:146`
  `except: return QueryAnalysis(ambiguous=False)` with no log → an ambiguous question gets a silent
  single interpretation, no "Assuming X", no clarification. **Fix:** distinguish hard-failure from a
  confident not-ambiguous verdict (log + status); `_plan_query` surfaces a degraded note when the
  gate tripped but analyze errored. **Shared** seam (Build uses `_plan_query`) — gate behavior so
  Build isn't forced into clarifications.

- **B9 · DO(careful) · A5 — `is_refusal` exact-match brittleness.** A near-refusal keeps its
  attached citations (`synthesize.py:23-32`). **Fix (low-risk):** keep exact-match contract but, when
  an answer carries citations yet `verify_answer` finds **zero** supported cited claims, surface
  insufficiency rather than presenting cited non-answers. **Shared** (is_refusal Ask-only). Some risk
  → careful tests.

- **B4 · DO(fold into B3) · §5 — "Citation Audit" overstates verification.** Counts
  `citations.length` as "CITED" (`CitationAudit.tsx`), ignoring `n_unsupported`. **Fix:** pass
  verification in; relabel center to a neutral count and/or add an unsupported indicator. Ask-only.

---

## Tier 3 — needs calibration / paid grading / human judgment (priority 1–2 but gated)

- **B7 · CAL · §9-7/A4/A5 — No retrieval coverage/defer gate.** Answer-vs-defer is delegated 100%
  to the model emitting REFUSAL; rerank/RRF scores are never thresholded (`rerank.py:18-28`,
  `query.py:223-250`). A real score floor must be **calibrated on the 67-Q benchmark** (paid LLM +
  human grading) to avoid false insufficiency, and it's **shared** with Dossier retrieval →
  **human/eval-gated; out of scope for an autonomous code change this run.** Document as the
  highest-impact known limitation.
- **B19 · CAL — Default verifier is lexical topicality, not entailment.** Shipping NLI as default
  adds a heavy dependency + needs benchmark calibration + shifts Dossier counts → **human decision.**
  Note as known limitation. (Negation/direction blindness is real.)

## Tier 4 — low value / latent / cost (deferred, logged so they aren't lost)

- **B14 LOW** — `run_ask_job` hardcodes `force=True` (latent; SPA never sends `force=false`). Thread
  `req.force` through. (`server.py:423`)
- **B15 LOW** — woven literature lane silent degrade (no user-visible "literature unavailable"
  marker). (`qa_stream.py:81-85`)
- **B16 LOW/cost** — no backend cancellation; closing the stream doesn't stop the daemon/paid synth.
- **B18 LOW** — `result.citations` is the retrieval set, not used-markers (benign: extra *real*
  sources; risky to prune mid-stream). Optional "mark uncited".
- **B20 LOW** — `[C#]` card chips would dangle if Ask ever emitted them (latent; Ask never emits
  `[C#]`). Defensive strip/gate.
- **B21 LOW** — `get_engine()` global cache ignores later `config` args (latent; single-config in
  practice). Document/assert.

## Refuted candidate defects (do NOT chase — verified false)
- Woven figure renumbering does **not** cause marker/source mismatch (`source_n` assigned once,
  reused identically). · Mid-stream failure is **not** silently swallowed (falls back to blocking
  + emits `error`/`done`; visible). · No PHI persistence concern (in-memory LRU-8, no question-text
  logging, single-user local tool).

---

### Planned execution order (smallest-coherent, safety-first, no-calibration-first)
B1 → B2 → B10 → B13 → B12 → B11 → B3 → B4(fold) → B5 → B17 → B6 → B8 → B9.
Re-evaluate after each; stop on any of the charter stop conditions. B7/B19 → CEO report as
human/eval-gated.

---

## STATUS AFTER PHASE 3 (final)

**Delivered (blind-evaluator gated):** B1, B2, B10, B13, B12, B11, B3, B17, B5 — all PASS /
PASS-with-limitations and committed. B6, B8 — implemented + tested + self-reviewed, in blind
evaluation at wrap-up (verdicts recorded in `EXPERIMENT_LOG.md` / `CEO_REPORT.md`).

**B4 (CitationAudit relabel) — SUPERSEDED / deferred.** B3 added a prominent needs-verification
banner surfacing the *real* verdict (unsupported / dangling / uncited-clinical), which addresses the
core "overstates verification" concern. The residual is the collapsed audit's "CITED" wording — a
**cosmetic** (priority-10) polish; deferred per the charter (don't promote easy/cosmetic work).

**B9 (cited non-answer → insufficiency) — DEFERRED as unsafe with the current verifier.** Adversarial
review: converting "verifier flagged all cited claims" into "no answer" would, given the **imprecise
default LexicalVerifier** (topicality, not entailment — see B19), risk **suppressing a genuinely
correct answer** (the dangerous direction — hiding a real answer). Safe only once a real entailment
(NLI) verifier is the default (B19). → human/eval-gated.

**Human/eval-gated (unchanged) — for the report, not autonomous change:**
- **B7** retrieval coverage/defer gate — needs benchmark calibration of a reranker-score floor + is
  shared with Dossier retrieval. Highest-impact remaining correctness lever.
- **B19** ship an NLI entailment verifier as default — adds a heavy dependency + needs calibration +
  shifts Dossier counts. Unblocks B9 and lifts A7 from topicality to real entailment.

**Low-value / latent (logged, not done):** B14 (force not forwarded — latent), B15 (woven lit lane
degraded marker), B16 (no stream cancellation — cost), B18 (mark uncited sources), B20 (`[C#]`
latent strip), B21 (`get_engine` cache doc).

**New follow-ups surfaced during execution (→ CEO report):**
- B5: unit-unaware digit match (a wrong "70 mmHg" missed if premise contains "70" elsewhere);
  spelled-out units/"percent" uncovered; decimals may soft-flag p-values/ORs. All under-flag/soft.
- B17: caption is a proxy for the figure image → a substantive non-matching caption soft-flags a
  figure-supported claim (needs-verification, never removal).
- B6: only suffix-bearing entities (-oma/-itis/…) + measurements detected; clinical terms without a
  suffix ("hydrocephalus", "aneurysm", "infarct") and pure-anatomy claims are NOT detected
  (under-detection, safe direction). A real clinical-sentence classifier would widen coverage.
- B2: a `LitCitation` with `n: null` would render `id="src-literature-null"` (backend
  data-consistency).
- B8: only operator-visible (logged); user-visible degraded state on a gate-trip+analyzer-outage is
  a larger Engine/answer-flow change.
