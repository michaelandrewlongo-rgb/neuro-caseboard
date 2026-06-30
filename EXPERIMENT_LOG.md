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

*(Phase 1 result + Phase 2 assessment appended once the baseline is frozen.)*
