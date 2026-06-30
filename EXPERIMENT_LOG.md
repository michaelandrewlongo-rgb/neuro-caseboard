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
