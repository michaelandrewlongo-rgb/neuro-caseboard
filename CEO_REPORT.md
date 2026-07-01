# CEO_REPORT — Neuro·Caseboard Autonomous Ask-Pathway Run

Acting owner/lead engineer report for an **experimental copy** of Neuro·Caseboard, scoped to the
**Ask** pathway (clinician free-text question → synthesized, citation-backed answer). Branch
`experiment/neuro-caseboard`, **local commits only** (never pushed). Original worktree untouched.

Throughout, claims are tagged: **[FACT]** = verified by running code/tests; **[JUDGMENT]** = my
assessment; **[ASSUMPTION]** = taken as given, not proven here; **[UNCERTAIN]** = open.

---

## 1. Executive summary

The Ask pathway's architecture is sound and matches an independently-derived ideal (retrieve →
synthesize → verify → attribute). Its **divergence from the frozen baseline was concentrated in the
safety keystone — the citation-verification gate** — which (a) silently accepted invented/dangling
citation markers as "supported", (b) never checked numbers (doses/thresholds), (c) didn't check
figure-cited claims, (d) couldn't flag uncited clinical claims, and (e) **was computed but never
shown to the user on the primary (web) surface**. Several failure states were also swallowed
silently (expired stream job, error-body start, refusal paired with a literature block).

**11 validated changes** were delivered, each the smallest coherent edit, each TDD-first, each gated
by an independent **Blind Evaluator** (fresh context; given only requirement + criteria + diff +
test output, never my rationale). The verification gate now surfaces dangling markers, model-
originated numerics, figure-cited claims, and uncited clinical claims, and the verdict is **rendered
to the clinician**. Failure states now surface visibly. One change (B5 numeric backstop) was caught
by its first Blind Evaluator as a real **FAIL** (a regex bug let wrong integer percentages pass),
was fixed, and re-passed — the gate working as designed.

**[JUDGMENT]** This run materially improved data integrity, correctness, and transparency of the
Ask pathway against the baseline's non-negotiables, with safe-direction trade-offs (it now flags
*more* for human verification, never hides). **It is NOT production-ready** — see §13/§16. For
clinical software, the absence of clinician sign-off alone means it is not, and several changes
alter the verification *output* and require clinician review (flagged below).

---

## 2. Clean-room baseline (frozen) — summary

`CLEAN_ROOM_BASELINE.md` was produced by an **isolated subagent with no repository access** (0 file
reads, 0 web calls), then frozen. It defined, independently of the code: personas (attending
mid-clinic, resident prepping, on-call 2 a.m., board/academic); the irreducible Ask jobs; the
synthesis↔citation contract ("a citation marker means *this passage supports this sentence*");
**§4 non-negotiables** (no invented markers; no citation–claim mismatch; entailment not topicality;
no model-originated numerics; fail visibly never silently; provenance-clean corpus; no PHI); latency
targets; an ideal architecture with an **authoritative verification gate** whose verdict is shown
post-gate; and **acceptance criteria A1–A13** + ten synthetic test workflows. The whole run was
measured against this yardstick. **[FACT]** It was never edited to conform to the code.

---

## 3. Initial repository assessment

Method: read the AI-generated Ask-pathway orientation map, then **verified every claim relied on
against current source** (the map's editorial "by design / fail-open" framing was stripped and each
behavior re-judged), plus a 6-dimension breadth-verification workflow. Full backlog in
`EXPERIMENT_BACKLOG.md`. Headline findings (all **[FACT]**, confirmed by reading source):

- **Verification gate under-reports / is advisory, not authoritative.** Dangling/invented markers
  abstain-into-"supported" (`answer_verify.py`); numbers are invisible to the lexical check
  (tokenizer drops <3-char tokens); figure-cited claims have an empty premise → abstain; uncited
  clinical sentences are auto-supported; the default verifier is lexical token-overlap (topicality,
  not entailment) unless an NLI model env var is set.
- **The verdict is invisible on the web (the primary surface).** It is computed + serialized + stored
  in the SPA store but **no component rendered it** — flagged and clean citations looked identical.
- **Default-path dangling `[L#]` chips.** Default woven mode sends `LiteratureSection(narrative="",
  citations=[…])`; the web `LiteratureBlock` returned `null` on empty narrative, so the PubMed source
  list never rendered and every inline `[L#]` chip dangled.
- **Silent failure states.** `startAsk` ignored `res.ok`/`job_id` → silent stuck loader; a fatal
  stream error (expired/evicted job 404) left the UI hung forever; `/api/ask/start`'s empty-question
  error omitted the `kind` discriminator; a textbook refusal was paired with a literature block.
- **No retrieval coverage/defer gate** (answer-vs-defer delegated entirely to the model emitting a
  refusal string) and **no PHI persistence concern** (in-memory LRU-8, no question logging).

Comparison vs baseline: **agrees** on architecture and on the figure-supporting carve-out; **diverges**
on verifier completeness/visibility and visible-failure; **contradicts** baseline A1/A2/A3/A6 in the
specific gate behaviors above. Three candidate defects were **refuted** and not chased (figure
renumbering mismatch; "partial-stream-swallowed" — it actually falls back + emits a visible error;
PHI persistence).

---

## 4. Inherited assumptions — preserved / modified / rejected

- **REJECTED — "a missing-premise marker is non-destructive (figure-only)."** A test encoded this;
  it conflated an *absent* source key with a figure-only *present-but-empty* key. Rejected per the
  charter (a test demonstrates behavior, not correctness): an absent key is a dangling marker and
  must flag (B1). The test was corrected to the production-accurate present-empty-key shape.
- **REJECTED — "uncited sentences are supported."** Replaced by a precision-first uncited-clinical
  flag (B6).
- **MODIFIED — "the verification verdict is advisory / display-optional."** Kept post-hoc (answer
  text is never mutated) but made it **visible** on the web and operator-observable for analyzer
  outages (B3, B8). Full *authoritative* gating (downgrading the answer body) remains out of scope.
- **MODIFIED — "figure-only citations carry no premise."** Now carry the caption (B17).
- **PRESERVED — fail-open robustness** of the literature lane and disambiguation analyzer (never
  block the answer), but made the analyzer outage observable (B8).
- **PRESERVED — exact-match refusal contract** (`is_refusal`); leaned on dropping spurious sources
  instead of loosening it (B10).
- **PRESERVED (flagged for humans) — the default lexical verifier**: not swapped for NLI (a heavy
  dependency + calibration + Dossier impact) → B19, human-gated.

---

## 5. Every completed change + commit + blind-evaluator verdict

Setup commits (process artifacts, not Ask-pathway code, not blind-gated):
`3c9f0ac` freeze baseline + preflight · `6476063` Phase-2 backlog.

| # | Commit | Change | Baseline | Verdict |
|---|--------|--------|----------|---------|
| 1 | `edf0392` | **B1** flag dangling/invented citation markers in `verify_answer` (+`dangling_markers()`, additive dict key, honest notice) | A1 | PASS |
| 2 | `b4a45ed` | **B2** render the `[L#]` PubMed list in default woven mode (`shouldRenderLiterature`) — chips no longer dangle | A1/A10 | PASS |
| 3 | `5595fbc` | **B10** drop the literature block on a textbook refusal (separate path; mirror woven) | A5 | PASS |
| 4 | `14c0282` | **B13** `/api/ask/start` empty-question error carries `kind` (parity with `/api/ask`) | A6 | PASS |
| 5 | `ac5467a` | **B12** `startAsk` validates `res.ok`/`job_id`, throws → visible "Request failed" card | A6 | PASS |
| 6 | `e592885` | **B11** fatal stream error (expired/evicted job 404) → visible "unavailable" + form re-enabled | A6 | PASS |
| 7 | `6e2ce95` | **B3** render the verifier verdict as an amber needs-verification banner (was computed, never shown) | A2/§4/A6 | PASS |
| 8 | `04189e6` | **B17** check figure-cited claims against the caption (was empty-premise abstain) | A3/A7 | PASS w/ lim |
| 9 | `6637855` | **B5** numeric backstop — model-originated dose/threshold/% flagged | A3 | PASS w/ lim (1st FAIL→fixed) |
| 10 | `43d6785` | **B8** disambiguation analyzer outage logged WARNING (was silent); decline stays DEBUG | A6 | PASS |
| 11 | `71c9f50` | **B6** flag uncited clinical sentences (named pathology/operation or measurement) | A2 (partial) | PASS w/ lim |

Each commit message records the change, the clinical-review flag where relevant, and its limitations.

---

## 6. Test & verification evidence  [FACT]

Verification path (the only CI gate is pytest): `python -m pytest` over `tests` + `vendor/caseprep/tests`,
the held-out `eval/quality_gate.py`, the wheel build, and a docker smoke. Web has a separate `vitest`
suite (not a Python-CI gate). Per-task: TDD (watched each test fail first), targeted regression,
self-review, Blind Evaluator. Final sweep on the committed state:

- **Python — 394 passed** across all changed-module suites + `tests/neuro_core` + `tests/evaluation`
  + `tests/test_cli.py` + `tests/test_briefing_synth.py` (2 pre-existing `table_names()` deprecation
  warnings, unrelated). `python -m compileall neuro_caseboard neuro_core app tests eval` — OK.
- **Web — 91 vitest passed** (15 files); `tsc --noEmit` clean; `eslint .` clean.
- **Held-out quality gate — `eval/quality_gate.py` → Gate: PASS** (all 16 metrics at baseline). I
  confirmed it is **independent of the answer-verification path** I modified (its metrics are
  coverage/intake/figure/contamination), so B1/B5/B6/B10/B17 cannot regress it — and it passed before
  and after.

**[UNCERTAIN]** The full ~17-min single-process pytest suite and the docker-smoke/package wheel CI
legs were **not** run end-to-end locally (time/sandbox); CI would run them. The scoped sweep covers
every module I changed and every consumer of it, but is not the complete suite.

---

## 7. Clinical-safety findings & changes flagged for clinician review

The following change what the system *reports as verified* and **require human clinician review**
(these automated gates catch regressions; they are **not** clinical validation):

- **B1** — an answer citing a source that does not exist now reports groundedness < 1.0 + a
  needs-verification notice (was silently "grounded"). Gate tightens only (adds flags, never removes;
  answer text untouched).
- **B5** — a dose/threshold/percentage absent from the cited premise now flags needs-verification.
  Safety-critical class; errs toward flagging. **Known gaps** (§13).
- **B6** — uncited named-pathology/operation or measurement sentences now flag. **Partial** (suffix-
  bearing entities + measurements only).
- **B17** — figure-cited claims now checked against the caption (soft flag, never removal).
- **B3** — the verifier verdict is now visible to the clinician (amber banner).

**[JUDGMENT]** All clinical-safety-relevant changes move in the safe direction: they surface *more*
uncertainty for human verification and never convert an uncertain result into a confident one, never
remove a citation, and never mutate the answer text. No clinical terminology, calculation, scoring
system, or recommendation was altered.

---

## 8. Data-integrity findings & changes  [FACT]

- Invented/dangling citation markers are no longer silently accepted (B1) — the flagship A1 fix.
- Default-path `[L#]` chips now resolve to a rendered, openable PubMed source list (B2).
- A textbook abstention is no longer paired with a literature source list (B10).
- The premise map now covers figure sources (B17), so figure-cited claims and their numerics are
  actually checked.
- No silent corruption was introduced: every gate change is additive to the serialized verification
  dict (new keys appear only when non-empty), so existing API/eval consumers are unaffected.

---

## 9. Security & privacy findings  [FACT]

- **No PHI handling concern** in the Ask path: question text is held in an in-memory LRU (cap 8), not
  persisted to disk, not logged (the breadth audit verified no question-text logging), and echoed
  only back to the originating client. No new persistence/transmission was added.
- No new dependency was introduced. No secrets touched/committed; `.env` remains gitignored. No
  auth/authorization/audit control was weakened. No repository content was sent to external services
  beyond the Blind Evaluator/assessment subagents operating **inside** this environment on the repo.
- **[ASSUMPTION]** The single-user local-tool threat model holds; a multi-user/persisted deployment
  would need question-text scrubbing/retention limits (pre-existing, noted in the backlog).

---

## 10. Known regressions

**[FACT] None identified.** The full scoped regression (394 Python + 91 web) and the held-out quality
gate all pass; the two pytest warnings are pre-existing and unrelated. Three existing tests were
**intentionally corrected** (not disabled) to reflect deliberately-changed behavior, each documented
and blind-evaluated: `test_missing_premise_is_non_destructive` → `test_figure_only_empty_premise_…`
(B1); the figure-citation `text==""` assertion (B17); the `verificationWarning` shape (B6). **[JUDGMENT]**
These are corrections of tests that encoded behavior contradicting the safety baseline, not concealed
regressions.

---

## 11. Unresolved risks & uncertainties

- **[UNCERTAIN] The default verifier is lexical (topicality), not true entailment.** It cannot detect
  negation/role-reversal, so a topically-overlapping but contradicted claim can still pass A7. The new
  backstops (dangling/numeric/bleed/uncited) tighten specific holes but do not make the core check an
  entailment check. → **B19 (human-gated).**
- **[UNCERTAIN] No retrieval coverage gate.** Answer-vs-defer is still delegated to the model emitting
  the refusal string; weak/zero-relevance retrieval still gets answered. The highest-impact remaining
  correctness lever, but it needs benchmark calibration of a score floor and is shared with Dossier
  retrieval. → **B7 (human/eval-gated).**
- **[UNCERTAIN] Numeric backstop is unit-unaware** (digit-presence match) → a wrong "70 mmHg" is
  missed if the premise contains "70" elsewhere; spelled-out units/"percent" uncovered; decimals may
  soft-flag p-values/odds-ratios. All safe-direction (under-flag / soft needs-verification).
- **[UNCERTAIN] B6 is a partial A2 net** (suffix-bearing entities + measurements only) — suffix-less
  clinical terms and pure-anatomy claims slip through (under-detection).
- **[JUDGMENT] Web component-render behavior** is verified via extracted pure-function predicates +
  TypeScript + reading the JSX (the repo has no jsdom/testing-library harness), not via DOM-render
  assertions. Low risk for these small conditional-render changes, but not browser-tested here.

---

## 12. Failed attempts

- **B5 (numeric backstop) — 1st Blind Evaluator FAIL.** The evaluator reproduced, end-to-end, that a
  trailing `\b` after the non-word `%` never matched, so integer percentages (a wrong `50%` carotid-
  stenosis threshold) passed silently. **Fix:** a dedicated `_PERCENT_NUM` pattern + dropping
  paraphrase-prone duration units (which were a cry-wolf surface). Re-evaluated → PASS-with-
  limitations. **No FAIL was ever committed** — this is the gate working as intended.
- **B6 — one evaluator run aborted** on a transient session/safety-classifier limit (no verdict
  returned). A fresh re-run returned PASS-with-limitations; nothing was committed without a completed
  verdict.

---

## 13. Remaining backlog (full list in `EXPERIMENT_BACKLOG.md`)

- **B7** retrieval coverage/defer gate — **human/eval-gated** (calibrate a reranker-score floor on the
  67-Q benchmark; shared with Dossier). *Highest-impact remaining correctness work.*
- **B19** ship an NLI entailment verifier as default — **human-gated** (heavy dep + calibration + shifts
  Dossier counts). Unblocks B9 and lifts A7 from topicality to entailment.
- **B9** cited-non-answer → insufficiency — **deferred as unsafe** with the current lexical verifier
  (would risk suppressing a genuinely correct answer — the dangerous direction). Safe only after B19.
- **B5/B6/B17 follow-ups** — unit-aware numeric matching; a real clinical-sentence classifier for A2
  recall; figure visual-content verification beyond captions.
- **B2 follow-up** — a `LitCitation` with `n: null` renders `id="src-literature-null"` (backend data
  consistency).
- **B4** (CitationAudit "CITED" relabel) — cosmetic; superseded by the B3 banner.
- Low-value/latent: B14 (force not forwarded), B15 (woven-lit degraded marker), B16 (no stream
  cancellation), B18 (mark uncited sources), B20 (`[C#]` strip), B21 (`get_engine` cache doc).

---

## 14. Decisions requiring human judgment

1. **Adopt an NLI entailment verifier as the default?** (dependency + cost + Dossier-count impact) —
   the single biggest lever on real answer-quality / A7, and a prerequisite for safely deferring on
   low-confidence answers (B9).
2. **Calibrate and enable a retrieval coverage floor (B7)?** Needs a graded benchmark run (paid LLM
   calls) and a Dossier regression pass.
3. **Clinician review** of every change that alters verification output (B1, B3, B5, B6, B17) before
   any non-experimental use.
4. **Verification posture:** keep the verdict advisory (current — answer shown, flags surfaced) or make
   it authoritative (downgrade/annotate the answer body inline)? The latter is a larger UX + safety
   decision.

---

## 15. Recommended next steps

1. Run the **full CI** (complete pytest suite + quality gate + wheel build + docker smoke) on the
   branch to confirm the legs not run locally.
2. **Clinician review** of the flagged changes; capture sign-off (or corrections) before any further use.
3. Prioritize **B19 (NLI default)** behind a feature flag with a calibrated threshold, validated on the
   67-Q benchmark *and* Dossier golden outputs (it is shared code).
4. Then **B7 (coverage floor)**, calibrated on the same benchmark to avoid false insufficiency.
5. Address the **B5 unit-aware numeric** follow-up and a real **B6 clinical-sentence classifier** to
   raise recall without sacrificing the precision-first stance.

---

## 16. Overall confidence

- **[FACT] High** that the 11 changes do what their commits claim, pass their tests + the held-out
  quality gate, introduce no detected regression, and were each independently blind-evaluated.
- **[JUDGMENT] Moderate-to-high** that they meaningfully improve the Ask pathway's data integrity,
  correctness, and transparency against the baseline's non-negotiables — with honest, safe-direction
  limitations (it flags more for human verification; it never hides failures or mutates answers).
- **[JUDGMENT] Low** that the Ask pathway is *complete* against the baseline: the core verifier is
  still lexical (not entailment) and there is still no retrieval coverage gate — both are the
  human/eval-gated items above.

**This project is NOT production-ready.** The evidence supports "materially improved and regression-
clean within the changed scope," not "validated for clinical use." Per the charter, for clinical
software the absence of clinician sign-off alone means it is not production-ready — and several
changes here alter verification behavior and explicitly require clinician review.

---

*Generated as the autonomous run's completion report. All commits are local to
`experiment/neuro-caseboard`; nothing was pushed, deployed, or shared externally.*

---

## ADDENDUM — cumulative adversarial review + retrieval A/B (post-completion, on request)

**Updated tally: 14 validated code commits** (the 11 above + 3 review-fix commits), plus process/doc
commits and one `chore(eval)` gitignore. All blind-evaluator-gated; no FAIL committed.

### A. Cumulative adversarial review (high value)
A holistic **find → verify** workflow over the cumulative 11-change diff (the per-change blind-evals
only saw each change in isolation) surfaced **5 CONFIRMED interaction findings**. **[FACT]** Four were
fixed (TDD + blind-eval PASS), one documented:

- **#3 [MED, fixed `d6650ed`]** — the streaming path verified the system disambiguation *prefix*
  ("**Assuming `<variant>`**") as a clinical claim; a variant label with a medical-suffix word (e.g.
  "hemicraniectomy") false-flagged the first sentence → a **false needs-verification banner on every
  disambiguated streaming answer**. This was a pre-existing latent mis-verification that **B3 made
  visible**. Fix: verify the body, matching the blocking path. *(This is exactly the kind of
  interaction a per-change review cannot catch — the strongest argument for the holistic pass.)*
- **#2 [MED, fixed `d6650ed`]** — a non-woven (`LITERATURE_WEAVE=false`) refusal could render beside
  sources (`_emit_batch` hardcoded `refusal:false`; B10 cleared only literature). Fix: full woven
  parity + `refusal:true` wire. (Mostly latent — the real `query()` already clears citations — but
  the wire-shape bug was real.)
- **#4 [LOW, fixed `a4aa827`]** — B8 narrowed `query_analyze`'s "never raises" contract (null-text hit
  → `TypeError`). Fix: guard + re-wrap. **[JUDGMENT]** a genuine regression I introduced.
- **#1 [LOW, fixed `a3c78e4`]** — `verification_notice` mislabeled numeric/bleed-only claims as "not
  entailed" + double-listed. Fix: `entailment_unsupported_markers()`.
- **#5 [MED, DOCUMENTED — not fixed]** — B17×B5: a co-cited figure caption's incidental number can
  satisfy B5's unit-unaware digit match, masking a fabricated dose. A deepening of B5's documented
  unit-unaware limitation; the robust fix (unit-aware numeric matching) has its own precision/recall
  tradeoff and **needs calibration → human/eval-gated follow-up.**

**[FACT]** All fixes regression-clean: 399 Python passed, `compileall` OK, `quality_gate.py` PASS.
**[JUDGMENT]** Net effect: the verification surfacing is now correct on the default streaming path,
and the gate's never-raises and refusal-parity contracts are restored.

### B. Retrieval A/B (pivot from B19)
**[FACT]** B19 (NLI verifier) was correctly judged **not answer-A/B-measurable** (advisory/post-hoc —
answer prose unchanged); on the user's decision we pivoted to **retrieval**, the bake-off-flagged
lever. **Single variable: `RERANK_K` 12 → 16**, synth held constant on Vertex `gemini-2.5-flash`
(free GCP credits), over a balanced 20-question subset (all 7 specialties). Smoke validated the
engine + the live-variable provenance gate (`rerank_k` recorded per arm).

**[FACT] Per the standing rule, the USER graded the blinded pairs.** The deliverable was
`PAIRS.md` (Answer-A / Answer-B, order randomized, arm labels hidden) + a blank `scoresheet.csv`;
I did **not** self-grade or unblind — the user returned the graded sheet (2026-07-01) and I unblinded
via `score.py`.

**[FACT] GRADED RESULT (n=20).** mean **87.45 (k=12) vs 88.40 (k=16), Δ +0.95, paired_t 2.29**
(just past the |t|>2 ≈ p<0.05 line — on the noise boundary at n=20); **head-to-head 14–6 for k=16,
0 ties**; six regressions, all ≤3 pts and **none from retrieval crowding** (the failure mode this arm
risked did not appear); k=16 **~23% slower at the median** (47.9s vs 39.0s). **[JUDGMENT] Verdict:
weak-positive, NOT decisive → the `RERANK_K` default is left UNCHANGED.** The direction favours k=16
and the crowding risk didn't materialise, but the effect is **<1 point on 100**, the t-stat is on the
noise boundary at n=20, and it was measured on a **cheap `gemini-2.5-flash` proxy, not the deploy
`glm-5.2`/`gemini-2.5-pro` synth**. Per the charter's "don't convert an uncertain result into a
confident output," flipping the default would need a **paid deploy-synth confirmation and ideally the
full 67-Q** — a budget decision for the user, not an autonomous spend. Logged to `evaluation/RESULTS.md`
**on master** (commit `9de8aa3`) as a prose subsection (not a table row — a subset+proxy Δ-vs-base
would mislead); experiment-log detail in `EXPERIMENT_LOG.md` (Phase 3c).
