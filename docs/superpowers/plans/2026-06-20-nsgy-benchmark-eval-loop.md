# Plan — Neuro·Caseboard 67-Question Benchmark-Driven Improvement System

**Goal (frozen in `.project-loop/STATE.md`):** Build and execute a reproducible benchmark-driven
improvement system over the 67-question *Contemporary Questions in Neurosurgery* benchmark. Generate
a frozen baseline, grade rigorously, find causally-attributable failure modes, map them to
components, implement targeted improvements, rerun, and prove genuine improvement without
regressions.

**Source files (preserve verbatim):**
- `/mnt/c/Users/Michael/Downloads/contemporary-qs-in-neurosurgery` — 67 questions, 7 sections.
- `/mnt/c/Users/Michael/Downloads/nsgy-questioner.txt` — runner protocol (UI-oriented; spec prefers direct API).
- `/mnt/c/Users/Michael/Downloads/nsgy-grader.txt` — practicing-neurosurgeon grading rubric.

**Frozen constraints:** only these 3 files + this local repo; no external repos/GitHub research;
preserve uncommitted work; no destructive git; do not modify production behavior until the baseline
is saved; never change benchmark/grader/prompts/model/corpus between baseline and comparison; never
fabricate grades/citations/verification/test results; deterministic scripts + machine-readable
artifacts; detailed experiment ledger.

**Stable ID scheme (verified counts):** NIS-01..08 (8), SPINE-01..09 (9), TUMOR-01..09 (9),
GENERAL-01..11 (11), OPEN-CV-01..10 (10), FUNCTIONAL-01..10 (10), TRAUMA-01..10 (10) = **67**.

**Regression gate (harness):** scoped pytest (`tests/neuro_core test_pipeline test_retrieve
test_qa`) with PYTHONPATH shadowing the worktree. Each step must keep this green. Steps that touch
only `evaluation/` keep it trivially green; the improvement steps (which touch production code) are
where the gate earns its keep.

**Budget note:** Phase 10's per-ticket Investigator/Planner/Implementer roles are realized as
durable ticket + root-cause + implementation-plan artifacts plus the actual code-change steps below,
rather than literally spawning 3 sub-agents per ticket (which would exhaust the increment budget).
This scoping is recorded honestly in the final summary.

## Steps

- [x] **Scaffold `evaluation/` and preserve inputs verbatim.** Create `evaluation/{inputs,runs,reports,scripts,schemas}` and `evaluation/reports/{root-causes,tickets}`. Copy the three source files byte-for-byte into `evaluation/inputs/` (no edits). Write `evaluation/inputs/SOURCE_CHECKSUMS.txt` (sha256 of each original + copy, proving fidelity). Write `evaluation/README.md` describing the framework layout, the ID scheme, and the reproduction entrypoints. Commit. (Touches only new files → harness stays green.)

- [x] **Repository audit → `evaluation/repository-audit.md`.** Inspect and document with exact file paths + symbols, separating facts from hypotheses: the `/ask` request path (frontend → API → engine), retrieval & ranking pipeline, figure/image retrieval, prompt assembly, citation generation & validation, corpus/metadata stores, model/provider configuration (expect Vertex/Gemini per CLAUDE.md), disambiguation behavior, error handling, logging/telemetry, existing tests & eval code, and env-var/config handling. Crucially: determine whether **direct in-process or HTTP API invocation** of `/ask` is possible (preferred over browser automation) and record the exact callable/endpoint + how to start the app. Commit.

- [x] **Normalize benchmark → manifest + schemas + verbatim validator.** Produce `evaluation/inputs/benchmark-manifest.jsonl` (67 records: `id, domain, source_number, question, benchmark_version, enabled`), each `question` copied verbatim from the source. Write JSON Schemas under `evaluation/schemas/` for manifest, run-record, grade-record, and defect-record. Write `evaluation/scripts/validate_manifest.py` AND a pytest test (`tests/evaluation/test_manifest.py`) asserting exactly 67 unique IDs, the per-section counts above, and that each question string is a substring of the source file (verbatim, normalization-altered-nothing). Add the new test to the harness path. Commit.

- [x] **Build the resumable runner (`evaluation/scripts/run_benchmark.py`).** Per Phase 2: sequential by default, configurable start/end IDs, per-question timeout, retry ladder matching `nsgy-questioner.txt` (immediate → 30s → 2nd retry → log engine-error), disambiguation detection + recording of the selected variant, full untruncated response capture, structured error states (`completed|engine_error|timeout|not_gradable`), atomic incremental per-question saves, resume without rerunning completed items, raw-response preservation, timing metrics, and a run-level config snapshot. Drive it through the **direct API** found in the audit (documented fallback if only HTTP/browser works). Write `tests/evaluation/test_runner.py` exercising resume + retry + error states against a **stub engine** (no live model). Add to harness. Commit.

- [ ] **Freeze + run the baseline (`evaluation/runs/baseline-<ts>/`).** Write a freeze manifest (git commit, dirty status, relevant config, model/provider identifiers, prompt hashes, corpus/index fingerprint, dependency-lockfile hashes, eval-script version, ISO datetime, host/runtime). Create an immutable `baseline-<ts>/` dir; run all 67 questions through the runner; preserve raw JSONL, human-readable Markdown, error log, timing summary, disambiguation log, and config manifest. **Engine-availability gate:** if the live engine (Vertex creds/ADC + LanceDB index) is operable, run for real; if not, record the limitation explicitly, mark every record `not_gradable` with `error_details`, and DO NOT fabricate answers. Commit (artifacts are immutable from here).

- [ ] **Grade the baseline (`evaluation/scripts/grade_run.py` + reports).** Apply `nsgy-grader.txt` as the authoritative rubric to every baseline answer; emit one grade record per answer (full schema: score, letter, clinical_usability, reason, got_right, minor_incompleteness, important_inaccuracies, safety_critical_errors, outdated_claims, missing_content, overabsolute_claims, evidence_anchors, confidence). Verify time-sensitive claims with available tools (WebSearch/PubMed/Scite) where feasible; otherwise label the dimension `verification_unavailable` — never invent verification. Record grader model, prompt hash, evidence date, settings; retain raw grader output. Produce `baseline-grades.jsonl`, `baseline-grades.md`, `baseline-summary.json`, `baseline-summary.md` with overall + per-domain mean/median/stddev, grade distribution, completion/error rate, median & p95 latency, unsafe-answer count, and evidence-verification coverage. Commit.

- [ ] **Failure analysis (`failure-ledger.jsonl` + reports).** For every grading criticism, write an atomic defect record using the controlled taxonomy (retrieval_*, citation_claim_mismatch, unsupported_claim, incorrect_synthesis, missing_*, overabsolute_language, disambiguation_failure, context_window_or_truncation, output_schema_inconsistency, engine_reliability, latency, grader_uncertainty, other) with severity, answer_excerpt, grader_basis, probable_layer, candidate_files, confidence, causal_status, recommended_action. Cluster across questions/domains; rank by `severity × frequency × causal_confidence × fixability` (frequency ≠ importance — a single safety-critical defect can top the list). Produce `evaluation/reports/failure-analysis.md` and `evaluation/reports/priority-matrix.md`. Commit.

- [ ] **Root-cause investigation for the top clusters (`evaluation/reports/root-causes/`).** For each high-priority cluster: trace the answer-generation path through the repo, reproduce the failure on the smallest example, inspect retrieved passages/scores/metadata/figures/prompt-context/citations, attribute the defect to a specific layer (query understanding/decomposition/retrieval/reranking/source-filtering/figure-retrieval/context-packing/prompting/synthesis/citation-rendering/UI/infra), record concrete repo evidence, assign causal confidence, and reject unsupported theories. One note per cluster. Commit.

- [ ] **Tickets + improvement proposals (`evaluation/reports/tickets/` + `implementation-plan.md`).** Create one ticket per distinct actionable failure mode (no per-question duplicates) with: failure-mode ID/category, severity/priority, affected questions, representative excerpts, observed-vs-expected, clinical/product impact, suspected layer, causal confidence, reproduction, acceptance criteria, regression-test requirements, artifact links, and labels (severity/subsystem/stage/status). Fold the Investigator (root-cause note) and Planner (per-change YAML in `implementation-plan.md`: change_id, defects_addressed, causal_evidence, files_and_symbols, proposed_change, expected_benefit, possible_regressions, questions_expected_to_improve, sentinel_questions_that_must_not_worsen, unit_tests, integration_tests, acceptance_criteria, rollback_method) into these artifacts. Require a supported root cause + measurable outcome + regression test + rollback path before any change is greenlit. Commit.

- [ ] **Implement targeted intervention #1 (highest-priority confirmed defect).** TDD: add a failing test/fixture first; make the smallest sufficient production change; run the harness + the new targeted test; rerun the affected benchmark questions and the sentinel (previously-strong) questions; record before/after in `evaluation/experiment-ledger.md` (change ID, files, hypothesis, before/after metrics, questions improved/worsened, safety-critical changes, latency, decision keep/revise/revert, evidence). Revert if it fails acceptance or causes clinically-meaningful regression. One coherent change only. Commit.

- [ ] **Implement targeted intervention #2 (next priority, budget permitting).** Same TDD + experiment-ledger discipline as #1; independent of #1 (no bundling of unrelated changes). If budget/causal-evidence does not support a second safe intervention, record that decision in the ledger and skip rather than forcing a change. Commit.

- [ ] **Final regression run + comparison (`evaluation/runs/post-improvement-<ts>/` + `final-comparison.md`).** Rerun the full frozen 67 under identical conditions where technically possible (same benchmark/grader/model/corpus). Compare baseline vs final by question and domain: score/grade/clinical-usability/safety-critical/failure-category/completion-rate/latency/citation-grounding deltas + any new regressions + comparability caveats. Use bootstrap CIs for aggregate score change; do not claim improvement on mean alone, and do not over-claim significance from a fixed 67-item set. Evaluate the success criteria (no increase in safety-critical errors, no unexplained deterioration of strong answers, targeted defects improved, stable/better completion, acceptable latency). Write `evaluation/reports/residual-risks.md`. Commit.

- [ ] **Root-level summary + full validation sweep (`NEURO_CASEBOARD_EVALUATION.md`).** Write the concise root summary (what was evaluated/changed/measurably improved/worsened/unresolved, strongly-supported vs uncertain conclusions, exact reproduction commands). Run the validation requirements: confirm exactly 67 verbatim questions, validate JSON/JSONL against schemas, confirm baseline artifacts were not overwritten, confirm every implemented change maps to ≥1 documented defect and has tests + before/after evidence, scan for secrets/credentials/PHI/absolute-local-paths/binary artifacts, run the applicable test/build commands, and review the final diff for unrelated edits. Report commands and actual outcomes honestly. Commit.
