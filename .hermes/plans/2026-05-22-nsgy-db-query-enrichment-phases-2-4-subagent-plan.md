# NSGY DB Query Enrichment Phases 2-4 Subagent Execution Plan

> **For Hermes:** Use `software-development/subagent-driven-development`. Dispatch one fresh ChatGPT Spark 5.3 subagent per task below. Do **not** make subagents read the original long plan; paste only the task packet they need.

**Goal:** Complete Phases 2-4 of NSGY DB query enrichment in small, test-first steps suitable for a smaller context-window coding subagent.

**Architecture:** Phase 2 adds a read-only local-corpus prior adapter that returns `PriorEnrichment` for the Phase 1 `query_enrichment` seam. Phase 3 additively exposes structured/enriched PubMed search helpers without changing public tool schemas unless contracts are intentionally updated. Phase 4 extracts best-available full-text retrieval into an internal retriever module with injected fetchers and no premature public-contract churn.

**Current baseline:** Phase 1 is implemented and green. Existing files of interest:
- `caseprep/query_enrichment.py` — Phase 1 contracts: `PriorEnrichment`, `ExpansionTerm`, `ExpansionProvenance`, `SeedSource`, `NeurosurgeryPriorAdapter`, `enrich_case_query(...)`.
- `caseprep/retrieval_planning.py` — exposes `build_enriched_retrieval_plan(...)`.
- `references/query-enrichment-nsgy-db-prior.md` — architecture rules.
- `caseprep/retrievers/corpus.py` — current local-corpus evidence retriever normalization.
- `caseprep/retrievers/pubmed.py` — current PubMed retriever normalization.
- `caseprep/mcp_server.py` — existing PubMed, local corpus, and get-fulltext handlers/helpers.

**Global constraints for every subagent:**
- Parser-derived `CaseSpec` facts are canonical. Do **not** infer or overwrite laterality, pathology, approach, or target from corpus priors.
- NSGY DB/local corpus is a retrieval prior only, not a claim generator.
- No real `/mnt/c/dev/NSGY_DB_lean` dependency in unit tests. Use temp SQLite fixtures.
- Missing corpus/fulltext DB must return warnings or empty records, not crash user-facing paths.
- Prefer read-only SQLite URI opens for real DB paths.
- Keep public MCP/FastAPI contracts unchanged unless the task explicitly updates contract fixtures and tests.
- Every implementer task must write or update tests first, run the targeted test, then run an affected suite.

**Controller workflow per task:**
1. Dispatch implementer subagent with the exact task packet.
2. Dispatch spec-review subagent with the task acceptance criteria and changed files.
3. If spec review fails, dispatch a fix subagent with the specific gaps.
4. Dispatch code-quality review subagent only after spec PASS.
5. Mark task complete only after targeted tests and affected suites pass.
6. Use a final integration-review subagent at the end of each phase.

**Standard implementer prompt preamble:**
```
You are implementing one small CasePrep task in /home/michael/projects/caseprep.
You have a smaller context window. Do not explore broadly. Read only the files named in this task packet plus directly imported helpers if needed.
Follow TDD: write/adjust tests first, run them to see the expected failure, implement the minimum, rerun tests.
Do not touch unrelated files. Do not commit. Return: changed files, exact tests run, pass/fail output summary, and any unresolved risks.
```

---

## Phase 2: NSGY_DB prior adapter

**Falsifiable phase goal:** `NeurosurgeryCorpusPrior(...).enrich(...)` can use a temp SQLite corpus fixture to produce deterministic, bounded `PriorEnrichment` terms, subdomain hints, seed sources, warnings, and quarantines, and can be injected into `enrich_case_query(..., retrieval_strategy="local_prior"|"hybrid")` without real DB/network access.

**Out of scope:** embeddings, graph infra, corpus curation/repair, claim synthesis, public API/schema changes, real NSGY DB integration tests.

**Phase 2 gate:** Run `python3 -m pytest tests/test_corpus_prior.py tests/test_query_enrichment.py tests/test_retrieval_planning.py -v` and then full suite.

### Task 2.1 — Create corpus prior contract tests with temp SQLite fixture

**Objective:** Lock expected adapter behavior before implementation.

**Files:**
- Create: `tests/test_corpus_prior.py`
- Create minimal stub if needed: `caseprep/retrievers/corpus_prior.py`

**Implementer packet:**
```
Create tests for a future `NeurosurgeryCorpusPrior` adapter. Use temp SQLite DBs only.

Required fixture schema (minimal; do not overbuild):
- works(id TEXT PRIMARY KEY, title TEXT, abstract TEXT, pub_year INTEGER, study_design TEXT, evidence_tier TEXT, citation_count INTEGER)
- subdomain_assignments(work_id TEXT, subdomain_id TEXT)
- identifiers(work_id TEXT, scheme TEXT, value TEXT)
- subjects(id INTEGER PRIMARY KEY, scheme TEXT, value TEXT)
- work_subjects(work_id TEXT, subject_id INTEGER)

Test cases:
1. `test_corpus_prior_returns_thrombectomy_subdomain_terms_and_seed_sources`
   - Build an M1 thrombectomy CaseSpec using `parse_case_input(...)` and `select_procedure_family(...)`.
   - Adapter returns `PriorEnrichment`.
   - Assert `stroke_thrombectomy` is in `subdomain_hints`.
   - Assert at least one `ExpansionTerm` includes thrombectomy/LVO/MCA-related aliases with provenance source `local_corpus`.
   - Assert seed source with PMID or DOI exists for a high-tier/high-citation fixture row.
   - Assert all returned terms have provenance and concept_type from Phase 1 allowed values.
2. `test_corpus_prior_quarantines_off_target_high_citation_terms`
   - Add an aneurysm/flow-diversion high-citation row in same DB.
   - For M1 thrombectomy, assert aneurysm/flow-diverter terms are in `quarantined_terms`, not `expansion_terms`.
3. `test_corpus_prior_missing_db_returns_warning_not_exception`
   - Use a nonexistent path.
   - Assert empty enrichment and a warning mentioning unavailable/missing DB.
4. `test_corpus_prior_aneurysm_subdomain_hint`
   - Use an aneurysm-ish CaseSpec (`ruptured MCA aneurysm coiling` is fine if parser degrades; pass family/profile as available).
   - Assert `aneurysm_sah` hint when fixture contains aneurysm rows.

Keep tests deterministic: sort outputs or compare sets.
Expected initial run: FAIL because module/class is missing or stub incomplete.
Run: `python3 -m pytest tests/test_corpus_prior.py -v`
```

**Spec-review checklist:** tests cover subdomain hinting, bounded terms, seed provenance, missing DB warning, and quarantine behavior using only temp SQLite.

### Task 2.2 — Implement read-only `NeurosurgeryCorpusPrior` skeleton and DB connection resolution

**Objective:** Make missing/available SQLite paths safe and deterministic.

**Files:**
- Modify: `caseprep/retrievers/corpus_prior.py`
- Test: `tests/test_corpus_prior.py`

**Implementer packet:**
```
Implement `NeurosurgeryCorpusPrior` enough to satisfy connection/missing-DB tests.

Required API:
- Constructor: `NeurosurgeryCorpusPrior(corpus_db: str | Path | None = None, *, term_limit: int = 24, seed_limit: int = 8)`.
- Defaults: use env `CASEPREP_CORPUS_DB`; if absent use `/mnt/c/dev/NSGY_DB_lean/corpus/neurointerventional.sqlite`.
- Open existing DB with SQLite URI read-only mode: `file:{path}?mode=ro` with `uri=True`.
- Close per `enrich(...)` call.
- If path missing/unreadable/schema missing, return `PriorEnrichment(warnings=(...))` instead of raising.
- Implement `enrich(case, family, profile) -> PriorEnrichment`.

At this task stage, it is OK if term extraction is still simple, but tests from Task 2.1 should pass or be adjusted only if they were over-specified.
Run: `python3 -m pytest tests/test_corpus_prior.py -v`.
```

**Spec-review checklist:** read-only URI, env/default path behavior, no exceptions on missing DB, no real DB required in tests.

### Task 2.3 — Add deterministic subdomain hinting and bounded term extraction

**Objective:** Produce useful prior terms while preventing broad/high-citation drift.

**Files:**
- Modify: `caseprep/retrievers/corpus_prior.py`
- Test: `tests/test_corpus_prior.py`

**Implementer packet:**
```
Implement deterministic prior extraction.

Rules:
- Determine candidate subdomains from case/family/profile keywords and fixture DB assignments.
  - M1/thrombectomy/LVO/stroke -> `stroke_thrombectomy`.
  - aneurysm/SAH/coiling/clipping -> `aneurysm_sah`.
- Query only candidate subdomains first.
- Extract candidate expansion aliases from `subjects.value`, title, and abstract using simple bounded heuristics.
- Term concept types should be conservative:
  - thrombectomy/stent retriever/aspiration/coiling/clipping -> `procedure` or `device` as appropriate.
  - MCA/M1/LVO/aneurysm -> `anatomy` or `pathology` as appropriate.
  - mRS/NIHSS/TICI/sICH -> `outcome`.
- Bound returned `expansion_terms` to `term_limit` and sort deterministically by confidence/citation/title.
- Every term gets `ExpansionProvenance(source="local_corpus", field_path=..., matched_value=...)`.
- Put off-target high-citation rows/terms into `quarantined_terms`, not `expansion_terms`, with provenance notes explaining off-target subdomain.

Run: `python3 -m pytest tests/test_corpus_prior.py tests/test_query_enrichment.py -v`.
```

**Spec-review checklist:** no unbounded alias growth; no case fact overwrite; provenance on every expansion; off-target terms quarantined.

### Task 2.4 — Add supplemental seed-source hints and merge behavior coverage

**Objective:** Corpus-derived high-quality identifiers supplement curated seeds without replacing them.

**Files:**
- Modify: `caseprep/retrievers/corpus_prior.py`
- Modify: `tests/test_corpus_prior.py`
- Possibly modify: `tests/test_query_enrichment.py` only if adding integration coverage

**Implementer packet:**
```
Add seed source generation from high-evidence/high-citation works.

Rules:
- A work can become a `SeedSource` if it has PMID/DOI/PMCID/work_id and evidence_tier in guideline/meta_analysis/RCT or high citation_count.
- Include `work_id` always when known; include PMID/DOI/PMCID from identifiers table.
- Do not fabricate citation fields.
- Bound to `seed_limit`, sorted deterministically: evidence tier priority, citation_count desc, pub_year desc, title.
- Provenance source must be `local_corpus`.
- Add or verify integration test showing `enrich_case_query(..., prior_adapter=NeurosurgeryCorpusPrior(...), retrieval_strategy="hybrid")` merges corpus seed with curated pack seeds. Duplicate PMID/DOI should merge provenance, not duplicate seed entries.

Run: `python3 -m pytest tests/test_corpus_prior.py tests/test_query_enrichment.py -v`.
```

**Spec-review checklist:** deterministic seeds, identifier dedupe compatible with Phase 1 merge, curated seeds preserved.

### Task 2.5 — Add prior-target divergence metadata without changing public contracts

**Objective:** Record self-bias risk when the same local corpus feeds prior and target retrieval.

**Files:**
- Modify: `caseprep/query_enrichment.py` if adding optional metadata field to `PriorEnrichment` is needed.
- Modify: `caseprep/retrievers/corpus_prior.py`
- Modify: `tests/test_corpus_prior.py` / `tests/test_query_enrichment.py`

**Implementer packet:**
```
Add conservative divergence reporting.

Preferred minimal design:
- Extend `PriorEnrichment` with optional `metadata: dict[str, Any] = field(default_factory=dict)` only if dataclass mutability/serialization is handled cleanly.
- `to_dict()` includes `metadata`.
- Adapter sets `metadata["prior_target_divergence"]` with:
  - `prior_sources`: e.g. `["local_corpus"]`
  - `target_sources`: e.g. `["local_corpus"]` if local corpus query emitted
  - `local_corpus_only_records`: count from fixture candidate rows lacking PMID/DOI/PMCID
  - `warnings`: list of divergence warnings/quarantine notes
  - `quarantined_count`
- If this touches Phase 1 tests, update expected JSON-shape tests additively.

Run: `python3 -m pytest tests/test_corpus_prior.py tests/test_query_enrichment.py tests/test_retrieval_planning.py -v`.
```

**Spec-review checklist:** additive serialization only; no public schema break; divergence warns about bias but does not block.

### Phase 2 integration review

**Reviewer packet:**
```
Review Phase 2 only.
Check:
- `NeurosurgeryCorpusPrior` implements `NeurosurgeryPriorAdapter` protocol by shape.
- All DB tests use temp SQLite and no real `/mnt/c/dev/...` access.
- Missing DB returns warnings, not exceptions.
- No parser facts are overwritten.
- Terms/seeds are bounded, deterministic, and provenance-bearing.
- Quarantine logic prevents off-target high-citation drift.
- Run or confirm: `python3 -m pytest tests/test_corpus_prior.py tests/test_query_enrichment.py tests/test_retrieval_planning.py -v`.
Verdict: APPROVED or REQUEST_CHANGES with exact fixes.
```

---

## Phase 3: PubMed/MCP structured search integration

**Falsifiable phase goal:** Existing `_handle_pubmed()` markdown output remains backward compatible by default, while private structured helpers can return query plan + articles for enriched PubMed retrieval under explicit additive strategy flags.

**Out of scope:** Changing public MCP tool schemas unless contract fixtures are deliberately updated; changing default search behavior; making network tests; full core-builder evidence tagging.

**Phase 3 gate:** `python3 -m pytest tests/test_web.py tests/test_contracts.py tests/test_pubmed_retriever.py tests/test_retrievers.py -v` plus full suite.

### Task 3.1 — Add private structured PubMed helper with injected fetchers

**Objective:** Create a testable helper that returns structured data without changing public handler behavior.

**Files:**
- Modify: `caseprep/mcp_server.py` or create helper module if simpler: `caseprep/retrievers/pubmed_structured.py`
- Test: create/update focused MCP/PubMed tests, likely `tests/test_pubmed_retriever.py` or new `tests/test_mcp_pubmed_structured.py`

**Implementer packet:**
```
Add a private helper for structured PubMed search. Prefer a small helper in a module if mcp_server.py is too large; if so import it from mcp_server.py later.

Required function shape in mcp_server.py namespace:
`async def _handle_pubmed_structured(args: dict) -> dict:`

Behavior:
- Accept existing args: `query`, `max_results`, `filter_type`, `include_abstracts`.
- Optional args: `query_plan`, `retrieval_strategy`.
- Return dict with keys:
  - `query`: original query string
  - `rendered_query`: query actually sent to PubMed
  - `query_plan`: provided plan or None
  - `retrieval_strategy`: strategy string, default `legacy`
  - `total`: PubMed total
  - `articles`: list of article dicts with `_relevance_score` and `_evidence_grade`
  - `markdown`: existing-style markdown formatting
- Tests must monkeypatch/inject PubMed search/summaries/abstracts; no network.
- Do not change `_handle_pubmed()` yet except imports if needed.

Run targeted test.
```

**Spec-review checklist:** structured helper is private, no public schema change, network mocked, markdown present.

### Task 3.2 — Route `_handle_pubmed()` through structured helper while preserving legacy output

**Objective:** Make legacy handler use the new helper internally and keep output unchanged by default.

**Files:**
- Modify: `caseprep/mcp_server.py`
- Test: existing/new MCP PubMed handler tests

**Implementer packet:**
```
Refactor `_handle_pubmed(args)` to call `_handle_pubmed_structured(args)` and return only `result["markdown"]` by default.

Add optional args handling:
- `retrieval_strategy`: allowed values `legacy`, `deterministic_enrichment`, `landmark_seeded`, `local_prior`, `hybrid`, `shadow`; default `legacy`.
- `return_query_plan`: if true, markdown may append a compact `## Query plan` section, but default output must remain old style.

Validation:
- Existing `_handle_pubmed` output tests should still pass or add snapshot-ish assertions that old headings remain.
- Invalid strategy should degrade to legacy with warning in structured result, not crash, unless current project style prefers explicit domain error.

Run: `python3 -m pytest tests/test_pubmed_retriever.py tests/test_contracts.py -v` and any new PubMed handler test file.
```

**Spec-review checklist:** default markdown compatibility; optional strategy is additive; contracts unchanged.

### Task 3.3 — Add additive web `/api/search` parameters behind existing route

**Objective:** Expose strategy/query-plan info to dashboard/API without breaking current response consumers.

**Files:**
- Modify: `caseprep/web.py`
- Test: `tests/test_web.py`

**Implementer packet:**
```
Add optional query params to existing `/api/search` only if route path/method remains unchanged:
- `retrieval_strategy: str = Query("legacy")`
- `return_query_plan: bool = Query(False)`

Behavior:
- Default response must remain compatible with current tests.
- If `return_query_plan` true, response includes additive `query_plan` / `retrieval_strategy` fields.
- Use existing `_safe_call()` pattern for external handler calls.
- Mock handlers in tests; no network.
- If contract fixture detects public OpenAPI change, treat it deliberately: either keep it hidden from schema if possible, or update contract fixture with explicit rationale and rerun contracts.

Run: `python3 -m pytest tests/test_web.py tests/test_contracts.py -v`.
```

**Spec-review checklist:** additive fields only; default behavior stable; safe error handling retained.

### Task 3.4 — Wire enriched query plans into structured PubMed helper without changing default behavior

**Objective:** Allow a caller to pass a Phase 1 enriched plan or case input and get PubMed queries from `RetrievalQuery.query_spec.render()`.

**Files:**
- Modify: `caseprep/mcp_server.py` or helper module from Task 3.1
- Test: PubMed structured tests

**Implementer packet:**
```
Add explicit enriched-search behavior under non-legacy strategies.

Rules:
- Default `legacy` still searches `args["query"]` exactly as before.
- If `query_plan` dict is provided and strategy != legacy, select PubMed queries from `query_plan["queries"]` where `retriever == "pubmed"`.
- For initial scope, search only the first PubMed query unless `max_axes` is provided; document this in result metadata.
- Return `query_plan` in structured result if requested.
- Do not parse free-text case input here unless existing plan already provides it; keep scope small.

Run: structured PubMed tests and contracts.
```

**Spec-review checklist:** no hidden behavior change; strategy path is explicit; uses structured query rendering from plan, not ad hoc string concatenation.

### Phase 3 integration review

**Reviewer packet:**
```
Review Phase 3 only.
Check:
- `_handle_pubmed()` default output remains backward-compatible.
- Public contract tests pass or fixture update is justified and explicit.
- All network interactions in tests are mocked/injected.
- Strategy handling is additive and rejects/degrades invalid values deterministically.
- `/api/search` still uses `_safe_call()` and clean error behavior.
Run/confirm: `python3 -m pytest tests/test_web.py tests/test_contracts.py tests/test_pubmed_retriever.py tests/test_retrievers.py -v`.
Verdict: APPROVED or REQUEST_CHANGES.
```

---

## Phase 4: Full-text retriever internals

**Falsifiable phase goal:** A new internal `FullTextRetriever` can fetch best-available content for a PMID through injected PMC/structured/plain/local providers, normalize it into `FullTextRecord`, and let `_handle_get_fulltext()` remain a formatter wrapper with existing text output preserved.

**Out of scope:** Public `core/contracts.py` changes, LLM synthesis over full text, new UI, changing citation/evidence schemas, network tests.

**Phase 4 gate:** `python3 -m pytest tests/test_fulltext_retriever.py tests/test_web.py tests/test_contracts.py -v` plus full suite.

### Task 4.1 — Add `FullTextRecord` and injected retriever tests

**Objective:** Define internal full-text result behavior with pure tests.

**Files:**
- Create: `caseprep/retrievers/fulltext.py`
- Create: `tests/test_fulltext_retriever.py`

**Implementer packet:**
```
Write tests first for internal fulltext retriever.

Expected API:
- `@dataclass(frozen=True) class FullTextRecord`
  - `pmid: str`
  - `tier: Literal["pmc_fulltext", "structured_abstract", "plain_abstract", "local_fulltext", "missing"]` or plain str if Literal is cumbersome
  - `text: str`
  - `sections: dict[str, str]`
  - `metadata: dict[str, Any]`
  - `warnings: tuple[str, ...] = ()`
  - `to_dict()` JSON-serializable
- `class FullTextRetriever`
  - constructor accepts injected async/sync callables for PMC fulltext, structured abstracts, plain abstracts, local fulltext.
  - `async retrieve(pmid: str) -> FullTextRecord`.

Test cases:
1. PMC fulltext wins over structured/plain.
2. Structured abstract wins over plain when PMC unavailable.
3. Plain abstract returned when only plain exists.
4. Missing all sources returns tier `missing` with warning, not exception.
5. Sync and async injected fetchers both work if practical; otherwise document async-only and keep implementation simple.

Run initial test to fail, implement minimal code, rerun.
```

**Spec-review checklist:** internal module only; injection-based; no network; JSON-serializable record.

### Task 4.2 — Wrap existing PubMed/PMC helpers by default injection

**Objective:** Connect `FullTextRetriever` defaults to existing mcp_server helpers while keeping tests mockable.

**Files:**
- Modify: `caseprep/retrievers/fulltext.py`
- Test: `tests/test_fulltext_retriever.py`

**Implementer packet:**
```
Add default fetchers that lazily import existing helpers from `caseprep.mcp_server`:
- `_pubmed_fulltext([pmid]) -> dict[pmid, text]`
- `_pubmed_structured_abstracts([pmid]) -> dict[pmid, sections]`
- `_pubmed_abstracts([pmid]) -> dict[pmid, text]`

Rules:
- Lazy import inside default functions to avoid circular imports.
- Any provider exception becomes a warning on the final record; continue to lower tiers.
- Do not call network in tests; tests use injected fakes.
- Preserve priority: PMC fulltext > structured abstract > plain abstract.

Run: `python3 -m pytest tests/test_fulltext_retriever.py -v`.
```

**Spec-review checklist:** lazy imports; provider exceptions degrade; priority order correct.

### Task 4.3 — Add optional local fulltext DB resolver

**Objective:** Let fulltext retriever use local fulltext DB when configured, without depending on real DB in tests.

**Files:**
- Modify: `caseprep/retrievers/fulltext.py`
- Test: `tests/test_fulltext_retriever.py`

**Implementer packet:**
```
Add local fulltext DB support behind injection/config.

Rules:
- Constructor accepts `fulltext_db: str | Path | None = None`.
- Default env var: `CASEPREP_FULLTEXT_DB`; if absent use `/mnt/c/dev/NSGY_DB_lean/fulltext/neurointerventional_fulltext.sqlite`.
- Open existing DB read-only with URI mode, close per call.
- If path missing/schema mismatch, add warning and continue to PubMed/PMC tiers.
- Test with temp SQLite fixture. Keep schema minimal and resolver tolerant: table can be whatever test defines, but implementation should use a clearly documented query. If unknown real schema, isolate query into one method for future adjustment.
- Local tier can be before or after PMC; prefer `local_fulltext` as a supplemental fallback unless plan says otherwise. Document chosen order in tests.

Run: `python3 -m pytest tests/test_fulltext_retriever.py -v`.
```

**Spec-review checklist:** no real DB in tests; read-only; missing DB warning; clear priority.

### Task 4.4 — Refactor `_handle_get_fulltext()` to formatter wrapper

**Objective:** Use internal retriever while preserving current MCP text output semantics.

**Files:**
- Modify: `caseprep/mcp_server.py`
- Test: `tests/test_web.py` and/or new handler tests

**Implementer packet:**
```
Refactor `_handle_get_fulltext(args)` to use `FullTextRetriever` and format its `FullTextRecord` into the existing text output.

Rules:
- Existing tool description says: PMC full text -> structured abstract -> plain abstract. Preserve that user-facing precedence unless local fulltext fallback was explicitly inserted as supplemental.
- Existing mocked web tests for get_fulltext must pass or be updated only if output is intentionally additive.
- Keep `_handle_get_fulltext(args) -> str` public behavior.
- Add private formatter function if helpful: `_format_fulltext_record(record: FullTextRecord) -> str`.
- Do not change MCP tool schema.

Run: `python3 -m pytest tests/test_fulltext_retriever.py tests/test_web.py tests/test_contracts.py -v`.
```

**Spec-review checklist:** handler is now wrapper; output compatible; contracts unchanged.

### Phase 4 integration review

**Reviewer packet:**
```
Review Phase 4 only.
Check:
- `caseprep/retrievers/fulltext.py` is internal and does not alter `core/contracts.py`.
- All fetchers are injectable; tests perform no network.
- Provider failures degrade with warnings.
- `_handle_get_fulltext()` output remains compatible and tool schema unchanged.
- Local fulltext DB access is read-only and optional.
Run/confirm: `python3 -m pytest tests/test_fulltext_retriever.py tests/test_web.py tests/test_contracts.py -v`.
Verdict: APPROVED or REQUEST_CHANGES.
```

---

## Final Phases 2-4 integration gate

Run after Phase 4 approval:

```bash
python3 -m pytest \
  tests/test_corpus_prior.py \
  tests/test_query_enrichment.py \
  tests/test_retrieval_planning.py \
  tests/test_pubmed_retriever.py \
  tests/test_retrievers.py \
  tests/test_fulltext_retriever.py \
  tests/test_web.py \
  tests/test_contracts.py \
  -v
python3 -m pytest -v
```

Final integration reviewer packet:
```
Review Phases 2-4 together.
Focus on seams and regressions:
- Query enrichment accepts `NeurosurgeryCorpusPrior` without forcing real DB.
- PubMed structured search can consume enriched plans but legacy default is unchanged.
- FullTextRetriever is internal and `_handle_get_fulltext()` remains compatible.
- No public schema drift unless explicitly fixture-updated.
- No tests depend on network or real NSGY DB.
- Full suite result is green.
Return: APPROVED/REQUEST_CHANGES with concrete file/path issues.
```
