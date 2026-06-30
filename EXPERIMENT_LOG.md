# EXPERIMENT_LOG — Neuro·Caseboard Autonomous Ask-Pathway Run

Running log of decisions, evidence, test results, failures, assumptions, uncertainties, and
completed work. Newest phase appended at the bottom. **Verified facts**, **agent judgments**,
**assumptions**, and **open uncertainty** are tagged inline.

---

## Ground rules in force (from the run charter)

- **Scope:** the **Ask** pathway only. Dossier / Cards / Build are *out of scope for improvement* —
  read-only, and any shared-code change must not break them (regression-check required).
- **Priority order:** data integrity → correctness → usability → helpfulness → reliability →
  clinical safety → responsiveness → maintainability → transparency → cosmetic.
- **Smallest coherent change per task.** No speculative rewrites. Reversible edits. One change per commit.
- **Never commit a FAIL** from the Blind Evaluator. Local commits only. No push/PR/deploy.
- **Synthetic data only.** No PHI. Do not weaken auditability, sourcing, error-visibility, or
  uncertainty reporting. Do not silently alter clinical terminology/calculations/recommendations.

---

## Phase 0 — Preflight  (VERIFIED FACTS)

- **Working dir** = `/home/michael/PROJECTS/neuro-caseboard/..neuro-caseboard-autonomous` — a **git
  worktree** (git-common-dir `/home/michael/PROJECTS/neuro-caseboard/.git`), distinct from the
  original worktree `/home/michael/PROJECTS/neuro-caseboard`. The original is **never touched**.
- **Branch:** started on `experimentautonomous-ceo` (clean tree); created + switched to
  **`experiment/neuro-caseboard`** for all work. Local commits only.
- **Verification path (the only CI gate is pytest):** confirmed against `.github/workflows/ci.yml`:
  - `sanity`: `python -m compileall` + pyproject TOML validity + no merge markers.
  - `test` (py3.10 & 3.12): `python -m pytest -p no:cacheprovider --durations=10` over
    `testpaths = ["tests", "vendor/caseprep/tests"]`, then `python eval/quality_gate.py` (3.12 leg).
  - `package`: `python -m build` + `twine check` + clean-room wheel install + `caseboard --help`.
  - `docker-smoke`: image build + `/api/health` engine:true.
  - `ci/local-ci.sh` reproduces sanity→test→quality_gate→package in a throwaway venv.
  - **ruff / eslint / mypy are NOT CI gates** (confirmed: ci.yml has no lint/type job).
- **Green baseline established:** scoped fast loop
  `python3 -m pytest tests/neuro_core tests/test_pipeline.py tests/test_retrieve.py tests/test_qa.py`
  → **263 passed in 6.90s**. Package is installed editable; imports resolve from the worktree
  (`pythonpath=["."]`).
- **Env note:** invoke Python as **`python3`** (`python` is not on PATH). Heavy ML libs are present
  in the user site-packages but tests inject fakes, so required-CI behavior is reproducible locally.

**Phase-0 verdict:** a working verification path exists (tests run green + build tooling present).
No STOP condition. Proceeded to Phase 1.

---

## Phase 1 — Clean-room baseline

- Spawned the **Clean-Room Strategist** as a fresh-context subagent with an explicit hard-isolation
  rule (no file reads, no repo access; optional web search for source-standard grounding). It
  returns the baseline as message text; I write the frozen file — so it never touches the repo.
- **Documented soft spot (per charter):** the subagent shares this model and there is no *hard*
  tool restriction available for "write-only / no-repo-read." The control is (a) the explicit
  instruction, (b) ordering (spawned before any app-source reading by the orchestrator), and
  (c) having it return content rather than write files. This removes the *rationale-anchoring*
  failure mode but not the shared-model prior. Stated plainly as required.

**Phase-1 result:** baseline produced with **0 tool calls** (fully isolated), frozen at
`CLEAN_ROOM_BASELINE.md`, committed (3c9f0ac). Soft spot recorded above stands.

---

## Phase 2 — Repository assessment (in progress)

**Method:** read the orientation map (`/mnt/c/Users/Michael/Downloads/neuro-caseboard-ask-pathway.md`),
then **verified its key claims against current source myself** (the charter: verify-don't-trust,
strip the "by design / fail-open" framing, judge each behavior against the frozen baseline). A
6-dimension breadth-verification **workflow** runs in parallel to re-confirm remaining claims at
current line numbers and surface anything missed.

### Source-VERIFIED findings (I read the code; current file:line)

- **[F1 · data-integrity · A1] Invented/dangling citation markers are silently counted as
  supported.** `answer_verify.verify_answer` builds `premise = " ".join(... premises.get(m) ...)`
  (`answer_verify.py:87`); an answer marker whose key is **absent** from the `premises` map yields
  an empty premise, and `should_cite("", …)` abstains→keep (`entailment.py:113-114`). The dangling
  marker is never counted in `n_unsupported` and never appears in `unsupported_markers`. The
  `premises` keys are exactly the real source set (`qa.py:201-204`, `qa.py:254-258`,
  `qa_stream.py:143-146`), so "key absent" reliably = "no such source" in the real pipeline.
  **Collides with baseline A1 (hard-zero invented markers) + failure-mode #4 (release-blocking).**
  Shared `verify_answer` ⇒ one fix covers blocking-woven, streaming, and non-woven paths.
  *Caveat:* test `test_answer_verify.py::test_missing_premise_is_non_destructive` currently pins the
  wrong behavior (`[3]` with `{}` premises ⇒ `n_unsupported==0`); its "figure-only" rationale is
  mistaken (a figure-only source *is* a present key with empty text). Fixing F1 requires correcting
  that test — allowed (charter), flagged for clinician review, not a concealed regression.
- **[F2 · data-integrity/transparency · A1/A10] Dangling `[L#]` chips in the DEFAULT path.** Default
  woven mode returns `LiteratureSection(narrative="", citations=[…])` (`qa.py:194-199`,
  `qa_stream.py:133-140`), but `web/.../LiteratureBlock.tsx:23` does `if (!literature.narrative)
  return null` — so the PubMed source list (the `src-literature-N` anchors the inline `[L#]` chips
  link to) is **not rendered**, leaving `[L#]` chips that resolve to nothing. **Baseline A1/A10.**
- **[F3 · transparency/safety · §4/§5] "Citation Audit" overstates verification.**
  `web/.../CitationAudit.tsx` gauges `citations.length` (the retrieval-derived *prompt* source list,
  not marker-derived, not entailment-checked) as "grounded/CITED" and never surfaces the backend
  `verification` (`n_unsupported`/`unsupported_markers`/`groundedness`), which is computed
  (`answer_verify.py`), serialized (`api/server.py:408-410,510`), stored in `askStore`, yet
  **unrendered**. Presents a confident "audit" that is really a source count. **Baseline §4 (don't
  overstate verification), §5 (verified-vs-unverified must be distinguishable).**
- **[F4 · uncited-claim blindness · A2] Uncited clinical sentences are auto-`supported`.**
  `answer_verify.py:83-84` appends any marker-less sentence as `supported=True`; the verifier cannot
  flag a clinical claim that carries no citation. Enforcement of "cite every clinical claim" is
  prompt-only (`woven_synth.WOVEN_SYSTEM`). **Baseline A2.** (Hard to fully solve — needs
  clinical-claim detection; candidate is a partial heuristic.)
- **[F5 · reliability · A6] `startAsk` ignores `res.ok`/`job_id`.** `web/src/lib/api.ts:132-137`
  returns the parsed body as `{job_id}` with no validation; a 422/5xx body ⇒ `job_id===undefined` ⇒
  stream opens to `/api/ask/stream/undefined` ⇒ silent stuck loader. **Baseline A6.**

### Breadth workflow (6 agents, 90 tool calls, 391k tok)

Independently re-confirmed F1–F5 at current line numbers and added: no numeric backstop (A3),
verifier verdict invisible on web (A2/§4), no retrieval coverage/defer gate (§9-7, **needs
benchmark calibration → human-gated**), analyzer fail-open silent (A12), figure-cited claims bypass
entailment (A3/A7), reconnect-to-expired-job hang (A6), separate-lane refusal+literature (A5),
`is_refusal` brittleness (A5). **Usefully REFUTED** three candidate defects so they aren't chased:
woven figure renumbering mismatch, partial-stream-swallowed (it falls back + emits visible
`error`), and PHI persistence (in-memory LRU-8, no question logging).

**Full prioritized plan → `EXPERIMENT_BACKLOG.md`.** Execution order (smallest-coherent,
safety-first, no-calibration-first): B1 → B2 → B10 → B13 → B12 → B11 → B3 → B4(fold) → B5 → B17 →
B6 → B8 → B9. B7 (retrieval coverage gate) and B19 (NLI default) are **human/eval-gated** (need the
67-Q benchmark + paid grading + Dossier regression) → deferred to the CEO report, not changed
autonomously.

**Phase-2 verdict:** assessment complete; the project largely *agrees* with the baseline on
architecture (retrieval → synthesis → post-hoc verify → attribution) but **diverges/contradicts** on
the safety keystone: the verification gate under-reports (dangling markers, numerics, uncited
claims), is advisory-not-authoritative, and is **invisible on the primary surface** — the exact
"overstates verification confidence" failure the charter flags. Proceeding to Phase 3.

---

## Phase 3 — Execution loop (validated changes)

Verification path: Python = `python3 -m pytest` (the only CI gate). Web = `cd web && npx vitest run`
(`npm ci` done; 75 existing tests green; **no DOM-render harness — convention is pure-function
`lib/` tests**, so web fixes extract a tiny testable predicate into `lib/`). Each change is the
smallest coherent edit, TDD-first, self-reviewed through the lenses, and **gated by a Blind Evaluator
given only requirement+criteria+diff+test-output (never my rationale)**. Never commit a FAIL.

| # | Task | Baseline | Blind verdict | Commit |
|---|------|----------|---------------|--------|
| 1 | **B1** dangling/invented citation markers flagged in `verify_answer` (+`dangling_markers()`, additive dict key, honest notice) | A1 (data integrity) | **PASS** | `edf0392` |
| 2 | **B2** render `[L#]` PubMed list in default woven mode (`shouldRenderLiterature` predicate; chips no longer dangle) | A1/A10 | **PASS** | `b4a45ed` |
| 3 | **B10** drop literature block on a textbook refusal (separate path; mirror woven) | A5 | **PASS** | `5595fbc` |
| 4 | **B13** `/api/ask/start` empty-question error carries `kind` (parity with `/api/ask`) | A6 | **PASS** | `14c0282` |
| 5 | **B12** `startAsk` validates `res.ok`/`job_id`, throws → visible "Request failed" card | A6 | **PASS** | `ac5467a` |
| 6 | **B11** fatal stream error (404 expired/evicted job) → visible "unavailable" + form re-enabled (`streamErrorState`) | A6 | **PASS** | `e592885` |
| 7 | **B3** verifier verdict surfaced as an amber needs-verification banner (`verificationWarning`; was computed but never rendered) | A2/§4/A6 | **PASS** | `6e2ce95` |
| 8 | **B17** figure-cited claims checked against the caption (was empty-premise abstain) | A3/A7 | **PASS+lim** | `04189e6` |
| 9 | **B5** numeric backstop — model-originated dose/threshold/% flagged | A3 | **PASS+lim** (1st FAIL caught `%` hole → fixed) | `6637855` |

| 10 | **B8** disambiguation analyzer outage logged WARNING (was silent); unparseable reply stays DEBUG | A6 | **PASS** | `43d6785` |
| 11 | **B6** uncited clinical sentences flagged (named pathology/operation or measurement) | A2 (partial) | **PASS+lim** | `71c9f50` |

**B5 FAIL→fix (the gate working):** the 1st blind eval reproduced a real false-negative — a trailing
`\b` after the non-word `%` never matched, so integer percentages (a wrong `50%` stenosis threshold)
silently passed. Fixed with a dedicated percent pattern + dropped paraphrase-prone durations; re-eval
PASS. **Documented limitations (B5):** digit match is unit-unaware (under-flag, safe); spelled-out
units/"percent" uncovered (under-flag); decimals may flag p-values/ORs (soft needs-verification).
**B17 limitation:** caption is a proxy for the figure image — substantive captions can soft-flag a
figure-supported claim (needs-verification, never removal; strictly more coverage).
**B6 limitation:** partial A2 net — only suffix-bearing entities + measurements; suffix-less terms
(hydrocephalus/aneurysm/infarct) and pure-anatomy claims not detected (under-detection, safe).

> **Evaluator-availability note:** one B6 evaluator run aborted on a transient session/safety-classifier
> limit (no verdict); a fresh re-run returned PASS-with-limitations. No change was committed without a
> completed blind-evaluator verdict.

---

## Phase 3 — close-out

**Stopped at 11 validated commits** (not the 25 cap) — a deliberate, charter-sanctioned early stop:
the high-value Ask-pathway data-integrity / correctness / safety / reliability / transparency gaps
the assessment found are addressed, and **every remaining backlog item is either human/eval-gated
(B7 retrieval-coverage floor, B19 NLI verifier — both need benchmark calibration + Dossier
regression), unsafe with the current verifier (B9 — would risk suppressing a real answer), or
cosmetic (B4 — superseded by B3).** Continuing would be padding, not value.

**Final regression (committed state) — VERIFIED:**
- Python: **394 passed** across every changed-module suite + `neuro_core` + `evaluation` + `cli` +
  `briefing`; `python -m compileall` OK (CI sanity gate).
- Web: **91 vitest passed**, `tsc --noEmit` clean, `eslint .` clean.
- Held-out **`eval/quality_gate.py` → Gate: PASS** (all 16 metrics at baseline; the gate is
  independent of the answer-verification path I modified).
- 11 commits, each its own coherent change, each blind-evaluator-gated. No FAIL committed.

---

## Phase 3b — Cumulative adversarial review + fixes (post-hoc, on request)

Ran a holistic adversarial **find → verify** workflow over the cumulative 11-change diff (the
per-change blind-evals checked each change in isolation; this hunts INTERACTIONS). 7 candidates →
**5 CONFIRMED** (each reproduced by an independent verify agent). Fixed the clean ones, each
TDD-first + blind-eval-gated:

| Finding | Sev | Fix | Verdict | Commit |
|---|---|---|---|---|
| #3 streaming verifies the disambiguation **prefix** → false needs-verification banner on disambiguated streaming answers (B3 surfaced a pre-existing mis-verification; verify body not prefix+body) | MED | verify `body` | **PASS** | `d6650ed` |
| #2 non-woven refusal could show beside sources (`_emit_batch` hardcoded `refusal:false`; B10 only cleared literature) → full woven parity + `refusal:true` wire | MED | (same commit) | **PASS** | `d6650ed` |
| #4 B8 moved the passages-join outside `try` → null-text hit raises (narrowed never-raises) | LOW | guard + re-wrap | **PASS** | `a4aa827` |
| #1 `verification_notice` mislabeled numeric/bleed-only claims as "not entailed" + double-listed | LOW | `entailment_unsupported_markers()` | **PASS** | `a3c78e4` |

**#5 [MEDIUM] — DOCUMENTED LIMITATION (not fixed):** B17×B5 interaction — a co-cited figure
caption's incidental number can satisfy B5's unit-unaware digit match, masking a fabricated dose.
This is a deepening of B5's already-documented unit-unaware limitation; the robust fix
(unit-aware numeric matching) has its own precision/recall tradeoff (a premise number stated
without a unit would then over-flag) and needs calibration → **follow-up, not an autonomous fix.**

**Take-away:** the holistic review was high-value — it caught a real default-path false-positive
(#3) that B3 *surfaced* and that no per-change review could see in isolation. **All fixes
regression-clean:** 399 python passed, compileall OK, `quality_gate.py` PASS.

---

## Phase 3c — Retrieval A/B (user pivot from B19)

B19 (NLI verifier) was correctly identified as **not answer-A/B-measurable** (advisory/post-hoc;
answer prose unchanged) — so on the user's call we **pivoted to retrieval**, the lever the bake-off
notes flag as the real, blind-A/B-measurable driver. **Single variable: `RERANK_K` 12 → 16**
(passages reaching synthesis; hypothesis: more grounded context → more comprehensive answers, at the
risk of retrieval crowding). Both arms held constant on Vertex `gemini-2.5-flash` (cheap/fast, free
GCP credits; the sandbox's DeepSeek path isn't wired on this branch — `make_synth_client` falls
through to Vertex). 20-question balanced subset (3 per specialty across all 7). Provenance gate
passed (smoke: `rerank_k=12` recorded, 3849-char cited answer). **Per the standing rule, the USER
grades the blinded pairs; I produce `PAIRS.md` + a blank scoresheet and never self-grade/unblind.**
*(Run + blinded pack status appended on completion.)*

**Regression evidence (after B1/B10):** held-out `eval/quality_gate.py` → **Gate: PASS** (all 16
metrics at baseline; the gate is independent of the answer-verification path). Web harness:
`npm ci` done, `npx vitest run` green throughout (no DOM harness in repo → web fixes extract a
testable `lib/` predicate per convention).

**🩺 CLINICIAN-REVIEW (B1):** changes verification *output* — an answer carrying a marker that
resolves to no source now reports groundedness < 1.0 + a needs-verification notice (previously
silently "grounded"). Gate tightens only (adds flags, never removes; answer text untouched). The
mis-named `test_missing_premise_is_non_destructive` (which used `{}` to stand in for a figure-only
source) was corrected to the production-accurate `{"3": ""}`; absent-key behavior is now covered by
new dangling tests — coverage increased, nothing hidden. *Known minor limitation:* a claim
co-citing a real-but-entailment-failing marker AND a dangling marker omits the real marker from the
human notice's "not entailed" line (still counted in `n_unsupported`/`unsupported_markers()`).
