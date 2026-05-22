# NSGY DB Query Enrichment Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a transport-neutral local neurosurgery-corpus prior layer that enriches CasePrep PubMed/PMC retrieval without silently rewriting patient-specific case facts.

**Architecture:** Keep the core `CaseSpec` parser as the source of patient/case facts, then add a new deterministic query-enrichment seam upstream of PubMed, PMC/full-text, and local corpus retrieval. The first implementation slice is pure and testable with fixtures; later phases wire the NSGY_DB SQLite corpus, MCP `search_pubmed`, full-text resolution, and core builder outputs through normalized `EvidenceRecord`/provenance structures.

**Tech Stack:** Python 3.10 dataclasses, pytest, existing CasePrep core modules (`case_parser.py`, `procedure_taxonomy.py`, `retrieval_planning.py`, `core/contracts.py`), SQLite read-only corpus access through existing NSGY_DB paths, existing MCP/FastAPI handlers.

---

## Product framing

CasePrep should treat NSGY_DB as a **transparent retrieval prior**, not as a black-box answer generator.

Post-review design constraints incorporated before implementation:

- **Laterality is query-purpose-specific, not globally banned.** Broad outcome/evidence searches strip laterality by default; targeted laterality-sensitive searches may include it only when the query declares an explicit case-fact policy and purpose.
- **PubMed queries are rendered from structured specs.** Generated PubMed strings must use MeSH terms where appropriate, `[tiab]` field tags for free text/acronyms, explicit date filters for current-evidence axes, and visible `omitted_terms`/warnings if bounded term lists are truncated.
- **Landmark seed sources are independent of NSGY_DB.** Curated evidence packs provide must-attempt PMIDs/DOIs even when the local corpus is missing, stale, or has corrupted identifiers.
- **Clinical applicability dimensions are first-class concepts.** Enrichment terms include `population`, `temporal_window`, and `imaging_modality`, not only procedure/anatomy/outcome terms.
- **CasePrep is not the corpus curation pipeline.** CasePrep consumes versioned local-corpus exports/adapters; metadata repairs, MeSH normalization, corpus coverage work, and schema evolution belong upstream in the corpus pipeline. This plan keeps the adapter seam narrow to reduce future consolidation/migration cost.

```text
free-text case
  -> CaseSpec parser
  -> ProcedureFamily + broad neurosurgical profile
  -> NSGY_DB/local-corpus prior layer
       - synonyms
       - anatomy/outcome/technique terms
       - subdomain hints
       - seed identifiers
       - query templates
       - provenance/warnings
  -> EnrichedRetrievalPlan
  -> PubMed / PMC Open / local corpus / radiology retrievers
  -> EvidenceRecord[] + ProvenanceRecord[]
  -> adapter
  -> web/MCP response and canonical operative dossier
```

Hard boundary:

- **Case facts** come from user input, parser, explicit structured input, or visible missing-fact prompts.
- **Literature priors** may expand/search/rank, but must not silently assert or overwrite case facts.

Example: `right M1 thrombectomy` preserves `laterality=right` in the structured case, but broad PubMed query expansion should use `M1 occlusion`, `middle cerebral artery occlusion`, `MCA occlusion`, and `anterior circulation large vessel occlusion`; it should not require `right` for broad outcome/evidence retrieval. A query may include `right`, `left`, `dominant hemisphere`, or approach-side language only when its `case_fact_policy` declares the query as laterality-sensitive and records why that matters. Valid laterality-sensitive examples include dominant-hemisphere awake mapping, AVM eloquence/mapping contexts, and approach-side spine queries such as LLIF.

---

## Current codebase observations

Relevant current files:

- `caseprep/core/contracts.py`
  - Existing normalized domain contracts: `BuildCasePlanRequest`, `BuildCasePlanResult`, `EvidenceRecord`, `ProvenanceRecord`, `ArtifactRef`.
  - `EvidenceRecord.metadata` is already the right extension point for matched concepts, query IDs, source tiers, and full-text tier.

- `caseprep/case_parser.py`
  - Produces `CaseSpec` with `procedure`, `pathology`, `approach`, `procedure_family`, `broad_profile`, `laterality`, `level_or_segment`, `anatomic_location`, missing critical facts, and degraded status.
  - `CaseSpec.to_dict()` already exists; `EnrichedRetrievalPlan.to_dict()` should intentionally call it rather than using raw `dataclasses.asdict()`.

- `caseprep/procedure_taxonomy.py`
  - Current known families: `spine_acdf`, `tumor_convexity_meningioma`, `posterior_fossa_chiari`, `endovascular_thrombectomy`.
  - Family retrieval templates already encode some deterministic domain expansions.

- `caseprep/profile_classifier.py`
  - Exposes `ProfileName` as a `Literal[...]`; query enrichment should use this type and validate public string inputs rather than accepting arbitrary profile strings.

- `caseprep/evidence_packs/thrombectomy.py`
  - Already contains a curated M1/anterior-circulation LVO thrombectomy evidence pack with landmark PMIDs/DOIs (MR CLEAN, ESCAPE, EXTEND-IA, SWIFT PRIME, REVASCAT, HERMES, DAWN, DEFUSE-3, guideline targets). Use this as the corpus-independent seed source before trusting NSGY_DB identifiers.

- `caseprep/retrieval_planning.py`
  - Current `build_case_queries(case, family)` returns PubMed-style `RetrievalAxis` objects.
  - This is the cleanest seam for adding an enriched retrieval plan without touching legacy MCP first.

- `caseprep/core/builder.py`
  - Calls `build_case_queries()`, retrieves PubMed/radiology/local corpus evidence, tags records, dedupes, synthesizes sections, builds provenance, and renders artifacts.
  - Current local corpus use is a single `provider_set.corpus.retrieve(topic, subdomain=..., top_n=max_per)` call after PubMed/radiology retrieval.

- `caseprep/retrievers/pubmed.py`
  - Normalizes PubMed search/summaries/abstracts into `EvidenceRecord` objects.

- `caseprep/retrievers/corpus.py`
  - Normalizes `_corpus_search()` output into `EvidenceRecord` objects.
  - Already protects FTS5 from hyphenated spine-level parsing via `_quote_spinal_level_terms()`.

- `caseprep/mcp_server.py`
  - MCP `search_pubmed` currently takes a raw query and returns formatted markdown.
  - `_handle_get_fulltext()` fetches PMID content through a 3-tier path: PMC full text -> structured abstract -> plain abstract.
  - `_corpus_search()` and `_corpus_get_paper()` already expose the local neurointerventional SQLite corpus and fulltext DB.

- `caseprep/web.py`
  - `/api/search` wraps `_handle_pubmed()`.
  - `/api/fulltext` wraps `_handle_get_fulltext()`.
  - Both must keep `_safe_call()` wrapping.

Contract-warning:

- `tests/test_contracts.py` compares public MCP tool schemas and FastAPI route lists against fixtures. Any public MCP schema or route changes must update `tests/fixtures/contracts/*.json` deliberately.

---

## Phase definitions

### Phase 1: Pure deterministic query-enrichment seam

**Goal:** A pure function turns a parsed `CaseSpec` + optional `ProcedureFamily` + profile into a JSON-serializable `EnrichedRetrievalPlan` with expansion terms, query objects, provenance, and warnings.

**Deliverable:**

```python
from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.query_enrichment import enrich_case_query

case = parse_case_input("mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion")
family = select_procedure_family(case)
plan = enrich_case_query(case, family, profile="vascular")
```

Output shape:

```json
{
  "case": {"raw_input": "...", "laterality": {"value": "right"}},
  "procedure_family": "endovascular_thrombectomy",
  "profile": "vascular",
  "retrieval_strategy": "deterministic_enrichment",
  "expansion_terms": [
    {
      "canonical": "M1 occlusion",
      "aliases": ["M1 occlusion", "middle cerebral artery occlusion", "MCA occlusion"],
      "concept_type": "anatomy",
      "confidence": 0.95,
      "provenance": [{"source": "case_parser.level_or_segment"}]
    },
    {
      "canonical": "late-window thrombectomy selection",
      "aliases": ["late window", "extended window", "6-24 hours", "perfusion imaging"],
      "concept_type": "temporal_window",
      "confidence": 0.85,
      "provenance": [{"source": "procedure_family_fixture"}]
    }
  ],
  "queries": [
    {
      "id": "pubmed_outcomes",
      "label": "Outcomes / Evidence",
      "retriever": "pubmed",
      "query": "(\"Thrombectomy\"[Mesh] OR \"mechanical thrombectomy\"[tiab]) AND ...",
      "query_spec": {
        "mesh_terms": ["Stroke", "Thrombectomy", "Middle Cerebral Artery", "Treatment Outcome"],
        "tiab_terms": ["acute ischemic stroke", "mechanical thrombectomy", "M1", "MCA", "mTICI", "modified Rankin Scale"],
        "date_filter": "2015/01/01:3000/12/31",
        "included_terms": [...],
        "omitted_terms": []
      },
      "case_fact_policy": {
        "laterality": "strip_for_broad_literature_search",
        "rationale": "Broad outcome literature is not right/left specific."
      },
      "purpose": "outcomes and landmark evidence",
      "axis": "outcomes",
      "provenance": [...]
    }
  ],
  "seed_sources": [
    {
      "id": "mr_clean",
      "title_hint": "A Randomized Trial of Intraarterial Treatment for Acute Ischemic Stroke",
      "pmid": "25517348",
      "doi": "10.1056/NEJMoa1411587",
      "provenance": [{"source": "caseprep.evidence_packs.thrombectomy"}]
    }
  ],
  "warnings": [
    "Only warn for ambiguity, truncation, missing seed fetches, or corpus/schema degradation — not for routine laterality stripping that is already recorded in case_fact_policy."
  ]
}
```

**Sections/status:**

| Capability | Status in Phase 1 | Source |
|---|---:|---|
| Parse case facts | Live | existing `case_parser.py` |
| Deterministic thrombectomy expansion | Live | in-code fixture in `query_enrichment.py` |
| JSON-serializable query objects | Live | new dataclasses + `to_dict()` |
| Optional prior adapter seam | Live but fake/tested only | injected test adapter |
| Live NSGY_DB SQLite inspection | Stub | Phase 2 |
| MCP/web behavior change | Out of scope | Phase 3 |
| Full-text/PMC resolver change | Out of scope | Phase 4 |
| Dossier rendering change | Out of scope | Phase 5/6 |

**Explicitly out of scope:**

- No live SQLite reads from NSGY_DB.
- No new public MCP tool.
- No change to default web/MCP output.
- No LLM calls.
- No graph database, embeddings, or dataset-joining infrastructure.
- No mutation of `case_parser.py` canonical parser behavior.
- No legacy MCP build-path rewrite.

**Acceptance criteria:**

1. `pytest tests/test_query_enrichment.py -v` passes.
2. `pytest tests/test_retrieval_planning.py -v` still passes.
3. `json.dumps(enrich_case_query(...))` succeeds.
4. `profile` is typed/validated against `caseprep.profile_classifier.ProfileName`; arbitrary strings do not silently drift into stored plans.
5. `right M1 ...` keeps `case.laterality.value == "right"`; broad PubMed queries exclude laterality and record `case_fact_policy.laterality="strip_for_broad_literature_search"`. Any query that includes laterality must declare a laterality-sensitive purpose/policy.
6. PubMed query objects include both rendered `query` and structured `query_spec` with MeSH terms when available, `[tiab]` free-text/acronym terms, date filters for current-evidence axes, and explicit `omitted_terms`/warnings if aliases are bounded.
7. M1 thrombectomy expansion includes anatomy, procedure, outcome, population, temporal-window, and imaging-modality concept types.
8. Every expansion term, query, seed source, and adapter contribution has non-empty provenance.
9. Landmark thrombectomy seed PMIDs/DOIs are present from the curated evidence pack even with no NSGY_DB adapter.
10. Unknown/degraded inputs produce warnings and generic query objects rather than forced procedure-family expansion.

---

### Phase 2: NSGY_DB prior adapter

**Goal:** A read-only corpus-prior adapter converts existing NSGY_DB SQLite metadata into bounded query-expansion candidates, supplemental seed-source hints, subdomain hints, warnings, and quarantine/conflict metadata. The adapter supplements — but never replaces — the curated landmark seed allowlist.

**Deliverable:**

```python
from caseprep.retrievers.corpus_prior import NeurosurgeryCorpusPrior
from caseprep.query_enrichment import enrich_case_query

prior = NeurosurgeryCorpusPrior()
plan = enrich_case_query(case, family, profile="vascular", neurosurgery_adapter=prior)
```

**Sections/status:**

| Capability | Status in Phase 2 | Source |
|---|---:|---|
| Subdomain hinting | Live | `subdomain_assignments` |
| Subject/keyword expansion | Live | `subjects`, `work_subjects` |
| Seed identifiers | Supplemental | `identifiers`, high evidence tier/citation count; merged with curated evidence-pack seeds |
| Adapter result contract | Live | `PriorEnrichment` with terms, seeds, subdomain hints, warnings, quarantined terms |
| Full section passages | Not directly consumed | Phase 4 |
| Live PubMed query execution | Out of scope | Phase 3 |

**Explicitly out of scope:**

- No final claim synthesis from local corpus alone.
- No asserting missing case facts from common literature terms.
- No broad epidemiology/registry matching behavior.
- No non-neurosurgery database discovery.

**Acceptance criteria:**

1. Adapter opens corpus DB read-only and closes every connection.
2. Missing DBs degrade to warnings, not crashes.
3. For M1 thrombectomy, adapter suggests `stroke_thrombectomy`, MCA/M1/LVO terms, outcome terms such as `mTICI`, `mRS`, `NIHSS`, and supplemental seed PMIDs/DOIs when present.
4. Curated evidence-pack seeds remain present if the adapter is unavailable, returns no identifiers, or disagrees with corpus metadata.
5. Adapter output is deterministic with fake SQLite fixtures.
6. Prior-target divergence is visible: if NSGY_DB is used as both query prior and retrieval target, the plan records shared dependency, independent PubMed/allowlist corroboration counts, and warnings/quarantine for local-corpus-only support.

---

### Phase 3: Enriched PubMed/MCP search

**Goal:** MCP `search_pubmed` and web `/api/search` can optionally use the enriched query plan while retaining old raw-query behavior by default or compatibility flag.

**Deliverable:**

```json
POST /api/search?query=right+M1+thrombectomy&retrieval_strategy=hybrid&return_query_plan=true
```

Response includes original query, expansion/query plan, formatted result text, and normalized metadata where available.

**Explicitly out of scope:**

- No route rename.
- No breaking existing `result` field expected by the dashboard tests.
- No default behavior change until regression and blind review pass.

**Acceptance criteria:**

1. Existing `/api/search` tests still pass.
2. New tests prove `retrieval_strategy="deterministic_enrichment"` uses enriched PubMed query string(s) without local-corpus adapter calls, and `retrieval_strategy="hybrid"` may additionally call the local prior adapter.
3. MCP schema fixture is updated only if public input schema changes.
4. Returned payload exposes expansion warnings/provenance/query specs when requested.
5. The default strategy remains `legacy` until Phase 5 eval and blind-review gates pass.

---

### Phase 4: Normalized PMC/full-text resolver

**Goal:** Move PMID/full-text resolution behind a retriever module that can use local fulltext DB first, then PMC Open, then structured/plain PubMed abstracts.

**Deliverable:**

```python
from caseprep.retrievers.fulltext import FullTextRetriever
record = await FullTextRetriever().resolve_pmid("25517348")
```

Output contains `source_tier`, citation identifiers, title, and structured passages.

**Acceptance criteria:**

1. Local fulltext DB hit returns `source_tier="local_fulltext"` and section passages.
2. PMC hit returns `source_tier="pmc_open"`.
3. Structured abstract fallback returns `source_tier="structured_abstract"`.
4. Plain abstract fallback returns `source_tier="abstract"`.
5. `_handle_get_fulltext()` becomes a formatting wrapper around the retriever.

---

### Phase 5: Core builder consumes enriched retrieval plan

**Goal:** `build_core_case_plan()` uses `EnrichedRetrievalPlan` for PubMed/local corpus/fulltext routing and stores the query plan in `result.structured["retrieval"]`.

**Deliverable:**

```bash
caseprep build "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion" -o /tmp/m1-enriched-caseprep
```

The generated `caseprep.yaml`/`provenance.json` and `07-evidence.md` show query expansion, source tiers, matched concepts, and warnings.

**Acceptance criteria:**

1. Existing canonical evals still pass.
2. M1 thrombectomy dossier includes mTICI/TICI, mRS, NIHSS, LVO/MCA/M1 language, temporal-window language, and imaging-selection language, but no unsupported laterality-derived literature claims.
3. Every `EvidenceRecord` from enriched retrieval has merged `metadata.query_ids`, `metadata.matched_concepts`, and `metadata.expansion_provenance` when applicable.
4. Evidence is deduplicated by PMID, DOI, PMCID, work_id, then normalized title before synthesis; dedup preserves merged query IDs, axes, matched concepts, and provenance.
5. Quarantined/off-target records remain excluded from deterministic synthesis.
6. Default-flip gate is explicit: landmark Recall@20 passes on a frozen held-out set, must-retrieve curated seeds are fetched or visibly reported missing, off-target/quarantined evidence rate stays below a defined threshold, deterministic eval does not regress, and blind clinical review passes a predefined rubric.

---

### Phase 6: Adapter/API transparency

**Goal:** Web/MCP adapter payloads can expose the query plan, warnings, evidence source tiers, and provenance without forcing dashboard users to read raw markdown.

**Deliverable:**

`/api/build` response optionally includes:

```json
{
  "query_plan": {...},
  "warnings": [...],
  "evidence_summary": {...},
  "artifacts": [...]
}
```

**Acceptance criteria:**

1. Existing stable response fields remain present: `slug`, `topic`, `output_dir`, `summary`, `caseplan_id`.
2. Structured fields are additive.
3. Dashboard DB persistence remains unchanged unless explicitly migrated.
4. Web tests cover both old and enriched payloads.

---

# Phase 1 detailed task plan

## Task 1: Add the RED test for JSON-serializable M1 enrichment

**Objective:** Prove the desired query-enrichment API exists and returns auditable, JSON-serializable query objects for an M1 thrombectomy case.

**Files:**
- Create: `tests/test_query_enrichment.py`
- Future create: `caseprep/query_enrichment.py`

**Step 1: Write failing test**

Create `tests/test_query_enrichment.py` with this initial test:

```python
"""Tests for deterministic query enrichment before external retrieval."""

from __future__ import annotations

import json

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.query_enrichment import enrich_case_query


def test_enrich_case_query_returns_json_serializable_m1_plan():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")

    json.dumps(plan)
    assert plan["case"]["laterality"]["value"] == "right"
    assert plan["procedure_family"] == "endovascular_thrombectomy"
    assert plan["profile"] == "vascular"
    assert plan["retrieval_strategy"] == "deterministic_enrichment"
    assert plan["expansion_terms"]
    assert plan["queries"]
    assert all(query["id"] for query in plan["queries"])
    assert all(query["query"] for query in plan["queries"] if query["retriever"] == "pubmed")
    assert all(query["query_spec"] for query in plan["queries"] if query["retriever"] == "pubmed")
    assert all(query["case_fact_policy"] for query in plan["queries"])
    assert all(query["provenance"] for query in plan["queries"])
```

**Step 2: Run test to verify failure**

Run:

```bash
python3 -m pytest tests/test_query_enrichment.py::test_enrich_case_query_returns_json_serializable_m1_plan -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'caseprep.query_enrichment'`.

**Step 3: Do not implement yet**

Stop after the RED failure. Task 2 creates the minimal module.

**Step 4: Commit after Task 2 passes, not now**

Do not commit a deliberately failing test alone unless the team workflow expects RED commits.

---

## Task 2: Create minimal query-enrichment contracts and function

**Objective:** Add the smallest `caseprep/query_enrichment.py` implementation that satisfies Task 1.

**Files:**
- Create: `caseprep/query_enrichment.py`
- Test: `tests/test_query_enrichment.py`

**Step 1: Keep Task 1 test as RED**

No additional test needed for this task.

**Step 2: Write minimal implementation**

Create `caseprep/query_enrichment.py`:

```python
"""Deterministic query enrichment between CaseSpec parsing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from caseprep.case_parser import CaseSpec
from caseprep.procedure_taxonomy import ProcedureFamily
from caseprep.profile_classifier import ProfileName

ConceptType = Literal[
    "procedure",
    "anatomy",
    "pathology",
    "approach",
    "outcome",
    "complication",
    "device",
    "study_design",
    "population",
    "temporal_window",
    "imaging_modality",
]
RetrieverName = Literal["pubmed", "pmc_open", "local_corpus", "radiology"]
RetrievalStrategy = Literal[
    "legacy",
    "deterministic_enrichment",
    "landmark_seeded",
    "local_prior",
    "hybrid",
    "shadow",
]
LateralityPolicy = Literal[
    "strip_for_broad_literature_search",
    "include_for_targeted_laterality_question",
    "not_applicable",
]

_VALID_PROFILES = {
    "skull_base",
    "supratentorial_tumor",
    "vascular",
    "spine",
    "posterior_fossa",
    "functional",
    "pediatric",
}
_LOCAL_PRIOR_STRATEGIES = {"local_prior", "hybrid"}


@dataclass(frozen=True)
class ExpansionProvenance:
    source: str
    field_path: str | None = None
    matched_value: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "field_path": self.field_path,
            "matched_value": self.matched_value,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExpansionTerm:
    canonical: str
    aliases: tuple[str, ...]
    concept_type: ConceptType
    confidence: float
    provenance: tuple[ExpansionProvenance, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "aliases": list(self.aliases),
            "concept_type": self.concept_type,
            "confidence": self.confidence,
            "provenance": [item.to_dict() for item in self.provenance],
        }


def _fielded_term(term: str, field: str) -> str:
    escaped = term.replace('"', r'\"')
    if any(char.isspace() for char in escaped) or "-" in escaped or "/" in escaped:
        return f'"{escaped}"[{field}]'
    return f"{escaped}[{field}]"


def _fielded_or(terms: tuple[str, ...], field: str) -> str:
    return "(" + " OR ".join(_fielded_term(term, field) for term in terms) + ")"


def _date_filter_clause(date_filter: str) -> str:
    start, end = date_filter.split(":", 1)
    return f'("{start}"[Date - Publication] : "{end}"[Date - Publication])'


@dataclass(frozen=True)
class PubMedQuerySpec:
    mesh_terms: tuple[str, ...] = ()
    tiab_terms: tuple[str, ...] = ()
    date_filter: str | None = None
    included_terms: tuple[str, ...] = ()
    omitted_terms: tuple[str, ...] = ()

    def render(self) -> str:
        groups: list[str] = []
        if self.mesh_terms:
            groups.append(_fielded_or(self.mesh_terms, "Mesh"))
        if self.tiab_terms:
            groups.append(_fielded_or(self.tiab_terms, "tiab"))
        if self.date_filter:
            groups.append(_date_filter_clause(self.date_filter))
        return " AND ".join(groups)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mesh_terms": list(self.mesh_terms),
            "tiab_terms": list(self.tiab_terms),
            "date_filter": self.date_filter,
            "included_terms": list(self.included_terms),
            "omitted_terms": list(self.omitted_terms),
        }


@dataclass(frozen=True)
class CaseFactPolicy:
    laterality: LateralityPolicy = "not_applicable"
    rationale: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"laterality": self.laterality, "rationale": self.rationale}


@dataclass(frozen=True)
class SeedSource:
    id: str
    title_hint: str
    provenance: tuple[ExpansionProvenance, ...]
    pmid: str | None = None
    doi: str | None = None
    pmcid: str | None = None
    work_id: str | None = None
    tier: str = ""
    conditional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title_hint": self.title_hint,
            "pmid": self.pmid,
            "doi": self.doi,
            "pmcid": self.pmcid,
            "work_id": self.work_id,
            "tier": self.tier,
            "conditional": self.conditional,
            "provenance": [item.to_dict() for item in self.provenance],
        }


@dataclass(frozen=True)
class RetrievalQuery:
    id: str
    label: str
    retriever: RetrieverName
    purpose: str
    axis: str
    query: str | None = None
    query_spec: PubMedQuerySpec | None = None
    case_fact_policy: CaseFactPolicy = CaseFactPolicy()
    identifiers: tuple[dict[str, str], ...] = ()
    provenance: tuple[ExpansionProvenance, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        rendered_query = self.query
        if rendered_query is None and self.query_spec is not None:
            rendered_query = self.query_spec.render()
        return {
            "id": self.id,
            "label": self.label,
            "retriever": self.retriever,
            "query": rendered_query,
            "query_spec": self.query_spec.to_dict() if self.query_spec else None,
            "case_fact_policy": self.case_fact_policy.to_dict(),
            "purpose": self.purpose,
            "axis": self.axis,
            "identifiers": list(self.identifiers),
            "provenance": [item.to_dict() for item in self.provenance],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PriorEnrichment:
    expansion_terms: tuple[ExpansionTerm, ...] = ()
    seed_sources: tuple[SeedSource, ...] = ()
    subdomain_hints: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    quarantined_terms: tuple[ExpansionTerm, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "expansion_terms": [term.to_dict() for term in self.expansion_terms],
            "seed_sources": [seed.to_dict() for seed in self.seed_sources],
            "subdomain_hints": list(self.subdomain_hints),
            "warnings": list(self.warnings),
            "quarantined_terms": [term.to_dict() for term in self.quarantined_terms],
        }


@dataclass(frozen=True)
class EnrichedRetrievalPlan:
    case: CaseSpec
    procedure_family: str | None
    profile: ProfileName
    retrieval_strategy: RetrievalStrategy
    expansion_terms: tuple[ExpansionTerm, ...] = ()
    queries: tuple[RetrievalQuery, ...] = ()
    seed_sources: tuple[SeedSource, ...] = ()
    prior_enrichment: PriorEnrichment = PriorEnrichment()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.to_dict(),
            "procedure_family": self.procedure_family,
            "profile": self.profile,
            "retrieval_strategy": self.retrieval_strategy,
            "expansion_terms": [term.to_dict() for term in self.expansion_terms],
            "queries": [query.to_dict() for query in self.queries],
            "seed_sources": [seed.to_dict() for seed in self.seed_sources],
            "prior_enrichment": self.prior_enrichment.to_dict(),
            "warnings": list(self.warnings),
        }


class NeurosurgeryPriorAdapter(Protocol):
    def enrich(
        self,
        case: CaseSpec,
        family: ProcedureFamily | None,
        profile: ProfileName,
    ) -> PriorEnrichment:
        ...


class LandmarkSeedProvider(Protocol):
    def seed_sources(
        self,
        case: CaseSpec,
        family: ProcedureFamily | None,
        profile: ProfileName,
    ) -> list[SeedSource]:
        ...


def _validate_profile(profile: str) -> ProfileName:
    if profile not in _VALID_PROFILES:
        raise ValueError(f"Unknown CasePrep profile: {profile!r}")
    return profile  # type: ignore[return-value]


def enrich_case_query(
    case: CaseSpec,
    family: ProcedureFamily | None,
    *,
    profile: ProfileName,
    retrieval_strategy: RetrievalStrategy = "deterministic_enrichment",
    neurosurgery_adapter: NeurosurgeryPriorAdapter | None = None,
    seed_provider: LandmarkSeedProvider | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable enriched retrieval plan.

    The enrichment layer may add literature-search priors, but it must not mutate
    or silently overwrite parser-derived case facts. `CaseSpec.to_dict()` is an
    intentional dependency of this transport-neutral boundary.
    """
    validated_profile = _validate_profile(profile)
    procedure_family = family.id if family is not None else case.procedure_family.value
    provenance = ExpansionProvenance(
        source="case_parser",
        field_path="case.raw_input",
        matched_value=case.raw_input,
        notes="baseline query from parsed case input",
    )
    terms: list[ExpansionTerm] = [
        ExpansionTerm(
            canonical=case.raw_input,
            aliases=(case.raw_input,),
            concept_type="pathology",
            confidence=0.5,
            provenance=(provenance,),
        )
    ]
    prior = PriorEnrichment()
    if neurosurgery_adapter is not None and retrieval_strategy in _LOCAL_PRIOR_STRATEGIES:
        prior = neurosurgery_adapter.enrich(case, family, validated_profile)
        terms.extend(prior.expansion_terms)
    warnings: list[str] = list(prior.warnings)

    seed_sources = tuple(seed_provider.seed_sources(case, family, validated_profile)) if seed_provider else ()
    baseline_spec = PubMedQuerySpec(
        tiab_terms=(case.raw_input,),
        included_terms=(case.raw_input,),
    )
    queries = (
        RetrievalQuery(
            id="pubmed_baseline",
            label="Baseline PubMed Query",
            retriever="pubmed",
            query_spec=baseline_spec,
            purpose="baseline literature retrieval from user-provided case text",
            axis="baseline",
            case_fact_policy=CaseFactPolicy(laterality="not_applicable"),
            provenance=(provenance,),
        ),
    )
    return EnrichedRetrievalPlan(
        case=case,
        procedure_family=procedure_family,
        profile=validated_profile,
        retrieval_strategy=retrieval_strategy,
        expansion_terms=tuple(terms),
        queries=queries,
        seed_sources=seed_sources,
        prior_enrichment=prior,
        warnings=tuple(warnings),
    ).to_dict()
```


**Step 3: Run test to verify pass**

Run:

```bash
python3 -m pytest tests/test_query_enrichment.py::test_enrich_case_query_returns_json_serializable_m1_plan -v
```

Expected: PASS.

**Step 4: Run nearby tests**

Run:

```bash
python3 -m pytest tests/test_query_enrichment.py tests/test_case_parser.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add caseprep/query_enrichment.py tests/test_query_enrichment.py
git commit -m "feat(core): add query enrichment seam"
```

---

## Task 3: Add RED test for thrombectomy-specific expansion terms

**Objective:** Prove M1 thrombectomy expands into clinically useful anatomy, technique, outcome, population, temporal-window, and imaging-selection terms.

**Files:**
- Modify: `tests/test_query_enrichment.py`
- Modify: `caseprep/query_enrichment.py`

**Step 1: Write failing test**

Append to `tests/test_query_enrichment.py`:

```python

def test_m1_thrombectomy_expands_anatomy_technique_and_outcomes():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")
    aliases = {
        alias.casefold()
        for term in plan["expansion_terms"]
        for alias in term["aliases"]
    }

    assert "m1 occlusion" in aliases
    assert "middle cerebral artery occlusion" in aliases
    assert "mca occlusion" in aliases
    assert "large vessel occlusion" in aliases
    assert "endovascular thrombectomy" in aliases
    assert "stent retriever" in aliases
    assert "aspiration thrombectomy" in aliases
    assert "mtici" in aliases
    assert "modified rankin scale" in aliases
    assert "nihss" in aliases
    assert "acute ischemic stroke" in aliases
    assert "anterior circulation lvo" in aliases
    assert "early window" in aliases
    assert "late window" in aliases
    assert "extended window" in aliases
    assert "6-24 hours" in aliases
    assert "ct angiography" in aliases
    assert "ct perfusion" in aliases
    assert "aspects" in aliases

    concept_types = {term["concept_type"] for term in plan["expansion_terms"]}
    assert {"population", "temporal_window", "imaging_modality"} <= concept_types
```

**Step 2: Run test to verify failure**

Run:

```bash
python3 -m pytest tests/test_query_enrichment.py::test_m1_thrombectomy_expands_anatomy_technique_and_outcomes -v
```

Expected: FAIL — missing expected aliases.

**Step 3: Write minimal implementation**

Patch `caseprep/query_enrichment.py` by adding deterministic thrombectomy fixtures above `enrich_case_query()`:

```python
_THROMBECTOMY_TERMS: tuple[ExpansionTerm, ...] = (
    ExpansionTerm(
        canonical="M1 occlusion",
        aliases=(
            "M1 occlusion",
            "middle cerebral artery occlusion",
            "MCA occlusion",
            "large vessel occlusion",
            "anterior circulation large vessel occlusion",
        ),
        concept_type="anatomy",
        confidence=0.95,
        provenance=(
            ExpansionProvenance(
                source="procedure_family_fixture",
                field_path="procedure_family.endovascular_thrombectomy",
                matched_value="M1/MCA occlusion",
                notes="bounded deterministic v1 expansion for thrombectomy retrieval",
            ),
        ),
    ),
    ExpansionTerm(
        canonical="mechanical thrombectomy",
        aliases=(
            "mechanical thrombectomy",
            "endovascular thrombectomy",
            "stent retriever",
            "aspiration thrombectomy",
            "balloon guide catheter",
            "distal access catheter",
        ),
        concept_type="procedure",
        confidence=0.95,
        provenance=(
            ExpansionProvenance(
                source="procedure_family_fixture",
                field_path="procedure_family.endovascular_thrombectomy.retrieval_templates",
                matched_value="mechanical thrombectomy",
            ),
        ),
    ),
    ExpansionTerm(
        canonical="reperfusion and functional outcome",
        aliases=(
            "TICI",
            "mTICI",
            "modified Rankin Scale",
            "mRS",
            "NIHSS",
            "first pass effect",
            "symptomatic intracranial hemorrhage",
            "sICH",
        ),
        concept_type="outcome",
        confidence=0.9,
        provenance=(
            ExpansionProvenance(
                source="procedure_family_fixture",
                field_path="procedure_family.endovascular_thrombectomy.eval_required_concepts",
                matched_value="TICI/mTICI/mRS/NIHSS",
            ),
        ),
    ),
    ExpansionTerm(
        canonical="anterior-circulation LVO acute ischemic stroke population",
        aliases=(
            "acute ischemic stroke",
            "anterior circulation LVO",
            "large vessel occlusion stroke",
            "proximal anterior circulation occlusion",
        ),
        concept_type="population",
        confidence=0.9,
        provenance=(
            ExpansionProvenance(
                source="procedure_family_fixture",
                field_path="procedure_family.endovascular_thrombectomy.population",
                matched_value="acute ischemic stroke anterior circulation LVO",
            ),
        ),
    ),
    ExpansionTerm(
        canonical="thrombectomy treatment time window",
        aliases=(
            "early window",
            "late window",
            "extended window",
            "6-24 hours",
            "6 to 24 hours",
            "tissue clock",
        ),
        concept_type="temporal_window",
        confidence=0.85,
        provenance=(
            ExpansionProvenance(
                source="procedure_family_fixture",
                field_path="procedure_family.endovascular_thrombectomy.temporal_window",
                matched_value="early/late/extended thrombectomy windows",
            ),
        ),
    ),
    ExpansionTerm(
        canonical="thrombectomy imaging selection",
        aliases=(
            "CT angiography",
            "CTA",
            "CT perfusion",
            "CTP",
            "perfusion imaging",
            "ASPECTS",
            "MRI selection",
        ),
        concept_type="imaging_modality",
        confidence=0.85,
        provenance=(
            ExpansionProvenance(
                source="procedure_family_fixture",
                field_path="procedure_family.endovascular_thrombectomy.imaging_modality",
                matched_value="CTA/CTP/ASPECTS/perfusion selection",
            ),
        ),
    ),
)
```

Then update `enrich_case_query()` after the baseline term:

```python
    if procedure_family == "endovascular_thrombectomy":
        terms.extend(_THROMBECTOMY_TERMS)
```

**Step 4: Run test to verify pass**

Run:

```bash
python3 -m pytest tests/test_query_enrichment.py::test_m1_thrombectomy_expands_anatomy_technique_and_outcomes -v
```

Expected: PASS.

**Step 5: Run all query enrichment tests**

```bash
python3 -m pytest tests/test_query_enrichment.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add caseprep/query_enrichment.py tests/test_query_enrichment.py
git commit -m "feat(core): add thrombectomy query expansions"
```

---

## Task 4: Add RED test for PubMed query specs and laterality policy

**Objective:** Enforce that broad PubMed queries preserve laterality in `CaseSpec` but exclude it from broad search strings via explicit per-query policy, while using fielded PubMed syntax, date filters, and visible truncation metadata.

**Files:**
- Modify: `tests/test_query_enrichment.py`
- Modify: `caseprep/query_enrichment.py`

**Step 1: Write failing test**

Append:

```python

def test_broad_pubmed_queries_use_fielded_terms_date_filter_and_laterality_policy():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")
    outcomes = next(query for query in plan["queries"] if query["id"] == "pubmed_outcomes")
    query = outcomes["query"].casefold()

    assert plan["case"]["laterality"]["value"] == "right"
    assert outcomes["case_fact_policy"]["laterality"] == "strip_for_broad_literature_search"
    assert "right" not in query
    assert "[mesh]" in query
    assert "[tiab]" in query
    assert "date - publication" in query
    assert outcomes["query_spec"]["date_filter"] == "2015/01/01:3000/12/31"
    assert outcomes["query_spec"]["omitted_terms"] == []
    assert not any("laterality preserved" in warning.casefold() for warning in plan["warnings"])
```

Append the no-silent-truncation regression:

```python

def test_pubmed_query_truncation_is_explicit_when_aliases_exceed_bound():
    from caseprep.query_enrichment import ExpansionProvenance, ExpansionTerm, PriorEnrichment

    class VerbosePrior:
        def enrich(self, case, family, profile):
            return PriorEnrichment(
                expansion_terms=(
                    ExpansionTerm(
                        canonical="verbose outcome aliases",
                        aliases=tuple(f"extra outcome term {idx}" for idx in range(10)),
                        concept_type="outcome",
                        confidence=0.5,
                        provenance=(ExpansionProvenance(source="fake_prior"),),
                    ),
                )
            )

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        neurosurgery_adapter=VerbosePrior(),
    )
    outcomes = next(query for query in plan["queries"] if query["id"] == "pubmed_outcomes")

    assert outcomes["query_spec"]["omitted_terms"]
    assert any("omitted" in warning.casefold() for warning in outcomes["warnings"])
```

**Step 2: Run tests to verify failure**

Run:

```bash
python3 -m pytest   tests/test_query_enrichment.py::test_broad_pubmed_queries_use_fielded_terms_date_filter_and_laterality_policy   tests/test_query_enrichment.py::test_pubmed_query_truncation_is_explicit_when_aliases_exceed_bound   -v
```

Expected: FAIL — no `pubmed_outcomes` query spec/policy yet, and truncation is not explicit.

**Step 3: Write minimal implementation**

Add helpers to `caseprep/query_enrichment.py`:

```python
def _aliases_for_type(terms: list[ExpansionTerm], concept_type: ConceptType) -> list[str]:
    seen: set[str] = set()
    aliases: list[str] = []
    for term in terms:
        if term.concept_type != concept_type:
            continue
        for alias in term.aliases:
            key = alias.casefold()
            if key not in seen:
                aliases.append(alias)
                seen.add(key)
    return aliases


def _bounded_aliases(aliases: list[str], *, limit: int = 24) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return included and omitted aliases; never truncate invisibly."""
    selected = tuple(aliases[:limit])
    omitted = tuple(aliases[limit:])
    return selected, omitted


def _broad_literature_policy(case: CaseSpec) -> CaseFactPolicy:
    if case.laterality.value:
        return CaseFactPolicy(
            laterality="strip_for_broad_literature_search",
            rationale="Broad evidence/outcome retrieval is not right/left specific; laterality remains in CaseSpec.",
        )
    return CaseFactPolicy(laterality="not_applicable")
```

Replace the single `pubmed_baseline` query construction with thrombectomy-specific query objects built from `PubMedQuerySpec`:

```python
    anatomy_aliases = _aliases_for_type(terms, "anatomy")
    procedure_aliases = _aliases_for_type(terms, "procedure")
    outcome_aliases = _aliases_for_type(terms, "outcome")
    population_aliases = _aliases_for_type(terms, "population")
    temporal_aliases = _aliases_for_type(terms, "temporal_window")
    imaging_aliases = _aliases_for_type(terms, "imaging_modality")

    if procedure_family == "endovascular_thrombectomy" and anatomy_aliases and procedure_aliases:
        broad_terms = procedure_aliases + anatomy_aliases + outcome_aliases + population_aliases + temporal_aliases + imaging_aliases
        included, omitted = _bounded_aliases(broad_terms, limit=24)
        query_warnings = ()
        if omitted:
            query_warnings = (f"PubMed query omitted {len(omitted)} bounded aliases; see query_spec.omitted_terms.",)
        outcomes_spec = PubMedQuerySpec(
            mesh_terms=("Stroke", "Thrombectomy", "Middle Cerebral Artery", "Treatment Outcome"),
            tiab_terms=included,
            date_filter="2015/01/01:3000/12/31",
            included_terms=included,
            omitted_terms=omitted,
        )
        technique_spec = PubMedQuerySpec(
            mesh_terms=("Thrombectomy", "Middle Cerebral Artery"),
            tiab_terms=tuple(procedure_aliases + anatomy_aliases + ["technique", "device", "stent retriever"]),
            date_filter="2015/01/01:3000/12/31",
            included_terms=tuple(procedure_aliases + anatomy_aliases),
        )
        queries = (
            RetrievalQuery(
                id="pubmed_outcomes",
                label="Outcomes / Evidence",
                retriever="pubmed",
                query_spec=outcomes_spec,
                purpose="broad outcomes and landmark thrombectomy evidence",
                axis="outcomes",
                case_fact_policy=_broad_literature_policy(case),
                provenance=(provenance, *_THROMBECTOMY_TERMS[0].provenance),
                warnings=query_warnings,
            ),
            RetrievalQuery(
                id="pubmed_technique",
                label="Surgical Technique",
                retriever="pubmed",
                query_spec=technique_spec,
                purpose="broad procedure-specific technique retrieval",
                axis="technique",
                case_fact_policy=_broad_literature_policy(case),
                provenance=(provenance, *_THROMBECTOMY_TERMS[1].provenance),
            ),
            RetrievalQuery(
                id="local_corpus_prior",
                label="Local Corpus Prior",
                retriever="local_corpus",
                query="mechanical thrombectomy M1 MCA large vessel occlusion",
                purpose="local neurosurgery corpus target retrieval; do not treat as independent of the corpus prior",
                axis="prior",
                case_fact_policy=_broad_literature_policy(case),
                provenance=(provenance,),
            ),
        )
    else:
        queries = (
            RetrievalQuery(
                id="pubmed_baseline",
                label="Baseline PubMed Query",
                retriever="pubmed",
                query_spec=baseline_spec,
                purpose="baseline literature retrieval from user-provided case text",
                axis="baseline",
                case_fact_policy=CaseFactPolicy(laterality="not_applicable"),
                provenance=(provenance,),
            ),
        )
```

Do **not** append a routine plan-level warning for laterality stripping. It is normal behavior recorded on each query's `case_fact_policy`. Warnings are reserved for ambiguity, truncation, missing seeds, adapter degradation, or corpus-prior conflicts.

**Step 4: Run tests to verify pass**

```bash
python3 -m pytest   tests/test_query_enrichment.py::test_broad_pubmed_queries_use_fielded_terms_date_filter_and_laterality_policy   tests/test_query_enrichment.py::test_pubmed_query_truncation_is_explicit_when_aliases_exceed_bound   -v
```

Expected: PASS.

**Step 5: Run full query enrichment tests**

```bash
python3 -m pytest tests/test_query_enrichment.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add caseprep/query_enrichment.py tests/test_query_enrichment.py
git commit -m "feat(core): render auditable PubMed query specs"
```

---

## Task 5: Add RED test for degraded/unknown input fallback

**Objective:** Prevent overconfident procedure-family expansion when input is underspecified.

**Files:**
- Modify: `tests/test_query_enrichment.py`
- Modify: `caseprep/query_enrichment.py`

**Step 1: Write failing test**

Append:

```python

def test_degraded_unknown_case_uses_baseline_query_with_warning():
    case = parse_case_input("vestibular schwannoma")
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="skull_base")

    assert plan["case"]["degraded"] is True
    assert plan["procedure_family"] in (None, plan["case"]["procedure_family"]["value"])
    assert [query["id"] for query in plan["queries"]] == ["pubmed_baseline"]
    assert plan["queries"][0]["query"] == '"vestibular schwannoma"[tiab]'
    assert plan["queries"][0]["query_spec"]["tiab_terms"] == ["vestibular schwannoma"]
    assert any("generic baseline" in warning.casefold() for warning in plan["warnings"])
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/test_query_enrichment.py::test_degraded_unknown_case_uses_baseline_query_with_warning -v
```

Expected: FAIL — no generic baseline warning yet.

**Step 3: Write minimal implementation**

In the non-thrombectomy/default branch of `enrich_case_query()`, add:

```python
        if case.degraded:
            warnings.append(
                "Using generic baseline query because the case is degraded or lacks a supported high-confidence procedure family."
            )
```

Then ensure the final plan uses `warnings=tuple(warnings)` rather than `warnings=prior.warnings`.

**Step 4: Run test to verify pass**

```bash
python3 -m pytest tests/test_query_enrichment.py::test_degraded_unknown_case_uses_baseline_query_with_warning -v
```

Expected: PASS.

**Step 5: Run all query enrichment tests**

```bash
python3 -m pytest tests/test_query_enrichment.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add caseprep/query_enrichment.py tests/test_query_enrichment.py
git commit -m "fix(core): degrade query enrichment conservatively"
```

---

## Task 5A: Add corpus-independent landmark seed allowlist

**Objective:** Ensure critical thrombectomy landmark PMIDs/DOIs come from a curated evidence pack, not from NSGY_DB metadata that may be stale, incomplete, or corrupted.

**Files:**
- Modify: `tests/test_query_enrichment.py`
- Modify: `caseprep/query_enrichment.py`
- Reuse: `caseprep/evidence_packs/thrombectomy.py`

**Step 1: Write failing test**

Append:

```python

def test_m1_thrombectomy_includes_curated_landmark_seeds_without_corpus_adapter():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")
    seeds_by_id = {seed["id"]: seed for seed in plan["seed_sources"]}

    for seed_id in ["mr_clean", "escape", "extend_ia", "swift_prime", "revascat", "hermes"]:
        assert seed_id in seeds_by_id
        assert seeds_by_id[seed_id]["pmid"]
        assert seeds_by_id[seed_id]["provenance"]
        assert seeds_by_id[seed_id]["provenance"][0]["source"] == "caseprep.evidence_packs.thrombectomy"

    assert seeds_by_id["mr_clean"]["pmid"] == "25517348"
    assert seeds_by_id["hermes"]["pmid"] == "26898852"
```

Append a dedup/provenance regression:

```python

def test_seed_sources_deduplicate_by_identifier_and_merge_provenance():
    from caseprep.query_enrichment import ExpansionProvenance, PriorEnrichment, SeedSource

    class DuplicateCorpusSeedPrior:
        def enrich(self, case, family, profile):
            return PriorEnrichment(
                seed_sources=(
                    SeedSource(
                        id="corpus_mr_clean_duplicate",
                        title_hint="MR CLEAN duplicate from corpus",
                        pmid="25517348",
                        doi="10.1056/NEJMoa1411587",
                        provenance=(ExpansionProvenance(source="fake_nsgy_db.identifiers"),),
                    ),
                )
            )

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        neurosurgery_adapter=DuplicateCorpusSeedPrior(),
    )
    mr_clean = [seed for seed in plan["seed_sources"] if seed["pmid"] == "25517348"]

    assert len(mr_clean) == 1
    assert {prov["source"] for prov in mr_clean[0]["provenance"]} == {
        "caseprep.evidence_packs.thrombectomy",
        "fake_nsgy_db.identifiers",
    }
```

**Step 2: Run tests to verify failure**

```bash
python3 -m pytest   tests/test_query_enrichment.py::test_m1_thrombectomy_includes_curated_landmark_seeds_without_corpus_adapter   tests/test_query_enrichment.py::test_seed_sources_deduplicate_by_identifier_and_merge_provenance   -v
```

Expected: FAIL — no default landmark seed provider and no seed dedupe/merge yet.

**Step 3: Write minimal implementation**

Add a default seed provider and merge helper:

```python
def _seed_identity(seed: SeedSource) -> tuple[str, str] | None:
    for field in ("pmid", "doi", "pmcid", "work_id"):
        value = getattr(seed, field)
        if value:
            return (field, value.casefold())
    return None


def _merge_seed_sources(*groups: tuple[SeedSource, ...]) -> tuple[SeedSource, ...]:
    merged: list[SeedSource] = []
    index: dict[tuple[str, str], int] = {}
    for group in groups:
        for seed in group:
            key = _seed_identity(seed)
            if key is None or key not in index:
                if key is not None:
                    index[key] = len(merged)
                merged.append(seed)
                continue
            existing = merged[index[key]]
            merged[index[key]] = SeedSource(
                id=existing.id,
                title_hint=existing.title_hint or seed.title_hint,
                pmid=existing.pmid or seed.pmid,
                doi=existing.doi or seed.doi,
                pmcid=existing.pmcid or seed.pmcid,
                work_id=existing.work_id or seed.work_id,
                tier=existing.tier or seed.tier,
                conditional=existing.conditional and seed.conditional,
                provenance=existing.provenance + seed.provenance,
            )
    return tuple(merged)


def _thrombectomy_evidence_pack_seeds(
    case: CaseSpec,
    family: ProcedureFamily | None,
    profile: ProfileName,
) -> tuple[SeedSource, ...]:
    if (family.id if family is not None else case.procedure_family.value) != "endovascular_thrombectomy":
        return ()
    from caseprep.evidence_packs.thrombectomy import ANTERIOR_CIRCULATION_LVO_M1

    provenance = ExpansionProvenance(
        source="caseprep.evidence_packs.thrombectomy",
        field_path="ANTERIOR_CIRCULATION_LVO_M1.items",
        matched_value="endovascular_thrombectomy",
    )
    return tuple(
        SeedSource(
            id=item.id,
            title_hint=item.title_hint,
            pmid=item.pmid,
            doi=item.doi,
            tier=item.tier,
            conditional=item.conditional,
            provenance=(provenance,),
        )
        for item in ANTERIOR_CIRCULATION_LVO_M1.items
        if item.pmid or item.doi
    )
```

Then merge default/evidence-pack, explicit seed-provider, and adapter seeds:

```python
    explicit_seed_sources = tuple(seed_provider.seed_sources(case, family, validated_profile)) if seed_provider else ()
    evidence_pack_seeds = _thrombectomy_evidence_pack_seeds(case, family, validated_profile)
    seed_sources = _merge_seed_sources(evidence_pack_seeds, explicit_seed_sources, prior.seed_sources)
```

**Step 4: Run tests to verify pass**

```bash
python3 -m pytest   tests/test_query_enrichment.py::test_m1_thrombectomy_includes_curated_landmark_seeds_without_corpus_adapter   tests/test_query_enrichment.py::test_seed_sources_deduplicate_by_identifier_and_merge_provenance   -v
```

Expected: PASS.

**Step 5: Run all query enrichment tests**

```bash
python3 -m pytest tests/test_query_enrichment.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add caseprep/query_enrichment.py tests/test_query_enrichment.py
git commit -m "feat(core): add landmark query seed sources"
```

---

## Task 6: Add fake prior-adapter merge test

**Objective:** Prove the future NSGY_DB adapter can contribute additional terms without requiring live SQLite in Phase 1.

**Files:**
- Modify: `tests/test_query_enrichment.py`
- Modify: `caseprep/query_enrichment.py`

**Step 1: Write failing test**

Append:

```python

def test_neurosurgery_adapter_terms_are_merged_with_fixture_terms():
    from caseprep.query_enrichment import ExpansionProvenance, ExpansionTerm, PriorEnrichment

    class FakePrior:
        def enrich(self, case, family, profile):
            return PriorEnrichment(
                expansion_terms=(
                    ExpansionTerm(
                        canonical="local corpus first pass effect",
                        aliases=("first pass effect", "first pass reperfusion"),
                        concept_type="outcome",
                        confidence=0.88,
                        provenance=(
                            ExpansionProvenance(
                                source="fake_nsgy_db",
                                field_path="subjects.value",
                                matched_value="first pass effect",
                            ),
                        ),
                    ),
                ),
                subdomain_hints=("stroke_thrombectomy",),
                warnings=("fake prior used for test",),
            )

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        neurosurgery_adapter=FakePrior(),
    )

    assert any(
        term["canonical"] == "local corpus first pass effect"
        and term["provenance"][0]["source"] == "fake_nsgy_db"
        for term in plan["expansion_terms"]
    )
    assert "stroke_thrombectomy" in plan["prior_enrichment"]["subdomain_hints"]
    assert any("fake prior" in warning for warning in plan["warnings"])
```

**Step 2: Run test to verify failure or pass**

```bash
python3 -m pytest tests/test_query_enrichment.py::test_neurosurgery_adapter_terms_are_merged_with_fixture_terms -v
```

Expected: FAIL until Task 2's `PriorEnrichment` protocol and the `hybrid` strategy branch are wired. If it passes immediately, mark this as already covered and do not change production code.

**Step 3: Minimal implementation if needed**

If the test fails, ensure `enrich_case_query()` includes:

```python
    prior = PriorEnrichment()
    if neurosurgery_adapter is not None and retrieval_strategy in _LOCAL_PRIOR_STRATEGIES:
        prior = neurosurgery_adapter.enrich(case, family, validated_profile)
        terms.extend(prior.expansion_terms)
```

Adapters must return `PriorEnrichment`, not a bare list of terms, so they can carry subdomain hints, supplemental seeds, warnings, and quarantined terms.

**Step 4: Run all query enrichment tests**

```bash
python3 -m pytest tests/test_query_enrichment.py -v
```

Expected: PASS.

**Step 5: Commit if code or tests changed**

```bash
git add caseprep/query_enrichment.py tests/test_query_enrichment.py
git commit -m "test(core): define corpus prior adapter seam"
```

---

## Task 7: Add retrieval-planning wrapper without changing existing live behavior

**Objective:** Expose the new enrichment seam from `retrieval_planning.py` while keeping existing `build_case_queries()` behavior and tests stable.

**Files:**
- Modify: `tests/test_retrieval_planning.py`
- Modify: `caseprep/retrieval_planning.py`

**Step 1: Write failing test**

Append to `tests/test_retrieval_planning.py`:

```python

def test_build_enriched_retrieval_plan_wraps_query_enrichment_for_m1():
    from caseprep.retrieval_planning import build_enriched_retrieval_plan

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = build_enriched_retrieval_plan(case, family, profile="vascular")

    assert plan["procedure_family"] == "endovascular_thrombectomy"
    assert any(query["id"] == "pubmed_outcomes" for query in plan["queries"])
    assert any(query["retriever"] == "local_corpus" for query in plan["queries"])
```

**Step 2: Run test to verify failure**

```bash
python3 -m pytest tests/test_retrieval_planning.py::test_build_enriched_retrieval_plan_wraps_query_enrichment_for_m1 -v
```

Expected: FAIL — `ImportError` or missing function.

**Step 3: Write minimal implementation**

Add imports near the existing retrieval-planning imports:

```python
from caseprep.profile_classifier import ProfileName
from caseprep.query_enrichment import RetrievalStrategy
```

Add to `caseprep/retrieval_planning.py` near `build_case_queries()`:

```python
def build_enriched_retrieval_plan(
    case: CaseSpec,
    family: ProcedureFamily | None,
    *,
    profile: ProfileName,
    retrieval_strategy: RetrievalStrategy = "deterministic_enrichment",
    neurosurgery_adapter=None,
) -> dict:
    """Build an auditable enriched retrieval plan without changing legacy axes."""
    from caseprep.query_enrichment import enrich_case_query

    return enrich_case_query(
        case,
        family,
        profile=profile,
        retrieval_strategy=retrieval_strategy,
        neurosurgery_adapter=neurosurgery_adapter,
    )
```

**Step 4: Run test to verify pass**

```bash
python3 -m pytest tests/test_retrieval_planning.py::test_build_enriched_retrieval_plan_wraps_query_enrichment_for_m1 -v
```

Expected: PASS.

**Step 5: Run old retrieval planning tests too**

```bash
python3 -m pytest tests/test_retrieval_planning.py -v
```

Expected: PASS. Existing assertions about `build_case_queries()` must not change in Phase 1.

**Step 6: Commit**

```bash
git add caseprep/retrieval_planning.py tests/test_retrieval_planning.py
git commit -m "feat(core): expose enriched retrieval planning seam"
```

---

## Task 8: Add documentation reference for the new seam

**Objective:** Record the architectural rule so future implementers do not route this through legacy MCP or make NSGY_DB a silent fact adjudicator.

**Files:**
- Create: `references/query-enrichment-nsgy-db-prior.md`

**Step 1: Write documentation**

Create `references/query-enrichment-nsgy-db-prior.md`:

```markdown
# Query enrichment with NSGY_DB as a local neurosurgery prior

CasePrep uses NSGY_DB as a transparent retrieval prior, not a black-box answer generator.

## Allowed

- Add synonyms, related terms, subdomain hints, outcome terms, anatomy-at-risk terms, query templates, seed identifiers, and warnings.
- Preserve provenance for every expansion.
- Use local corpus metadata to improve PubMed/PMC retrieval.

## Not allowed

- Silently overwrite parser-derived case facts.
- Infer laterality, pathology, approach, or operative target from the most common literature cluster.
- Generate final clinical claims from local corpus priors without `EvidenceRecord` provenance.
- Build graph/embedding infrastructure before deterministic SQL-backed prior is validated.

## Laterality rule

Laterality is a case fact for operative reasoning and rendering. It is usually excluded from broad PubMed/PMC literature search strings unless the search purpose explicitly requires laterality. Laterality-sensitive retrieval examples include dominant-hemisphere/awake mapping literature, AVM eloquence or mapping queries, and spine approach-side questions such as LLIF. The decision is recorded per query in `case_fact_policy`; routine broad-query stripping should not create noisy user-facing warnings.

## PubMed query rule

PubMed queries must be rendered from structured query specs. Use MeSH terms where appropriate, `[tiab]` field tags for free-text terms and acronyms, explicit publication-date filters for current-evidence axes, and `omitted_terms` metadata when bounded alias lists are truncated.

## Seed-source rule

Landmark seed PMIDs/DOIs come first from curated CasePrep evidence packs, not from NSGY_DB. Corpus-derived identifiers may supplement and add provenance, but must not replace curated seeds. Duplicate seed sources are merged by PMID, DOI, PMCID, or work_id while preserving provenance.

## Corpus boundary

CasePrep consumes local corpus exports/adapters; it is not the corpus curation pipeline. Metadata repairs, MeSH normalization, coverage updates, and schema evolution belong upstream. The adapter should validate schema/version and degrade with warnings when the corpus is unavailable or inconsistent.
```

**Step 2: Verify docs file exists**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('references/query-enrichment-nsgy-db-prior.md')
assert p.exists()
assert 'transparent retrieval prior' in p.read_text()
PY
```

Expected: exits 0.

**Step 3: Commit**

```bash
git add references/query-enrichment-nsgy-db-prior.md
git commit -m "docs: define NSGY DB query prior rules"
```

---

## Task 9: Run Phase 1 regression suite

**Objective:** Verify the pure seam did not disturb current core behavior.

**Files:**
- No edits expected.

**Step 1: Run targeted tests**

```bash
python3 -m pytest \
  tests/test_query_enrichment.py \
  tests/test_retrieval_planning.py \
  tests/test_case_parser.py \
  tests/test_procedure_taxonomy.py \
  tests/test_core_builder.py::test_core_builder_retrieves_with_family_template_queries_for_acdf \
  -v
```

Expected: PASS.

**Step 2: Run contract tests**

```bash
python3 -m pytest tests/test_contracts.py -v
```

Expected: PASS. If this fails, Phase 1 accidentally changed public MCP/FastAPI contracts and must be reverted or explicitly migrated.

**Step 3: Run full suite if targeted tests pass**

```bash
python3 -m pytest -v
```

Expected: PASS.

**Step 4: Capture status**

```bash
git status --short --branch
```

Expected: clean working tree after commits, or only intentional uncommitted files.

---

# Phase 2 task skeleton: NSGY_DB prior adapter

Do not start Phase 2 until Phase 1 is green and committed.

## Task 2.1: Add fake SQLite fixture test for corpus prior

**Files:**
- Create: `tests/test_corpus_prior.py`
- Create: `caseprep/retrievers/corpus_prior.py`

Test should create a temp SQLite DB with minimal tables mirroring:

```sql
works(id, title, pub_year, study_design, evidence_tier, citation_count)
works_fts(title, abstract) -- optional if using normal table in fixture
subdomain_assignments(work_id, subdomain_id)
identifiers(work_id, scheme, value)
subjects(id, scheme, value)
work_subjects(work_id, subject_id)
```

Acceptance: `NeurosurgeryCorpusPrior(...).enrich(...)` returns a deterministic `PriorEnrichment` with bounded, provenance-bearing terms, subdomain hints, supplemental seeds, warnings, and quarantined off-target terms for thrombectomy without opening real `/mnt/c/dev/NSGY_DB_lean`. Include fixture rows that would otherwise overfit the prior/target loop and assert off-target high-citation terms are quarantined.

## Task 2.2: Implement read-only connection resolution

**Files:**
- Modify: `caseprep/retrievers/corpus_prior.py`

Use env vars:

```python
CASEPREP_CORPUS_DB
CASEPREP_FULLTEXT_DB
```

Default to existing NSGY_DB paths used by `mcp_server.py`. Open read-only with URI mode and close per call.

## Task 2.3: Add subdomain hinting

Acceptance: M1 thrombectomy returns `stroke_thrombectomy`; aneurysm returns `aneurysm_sah`; missing DB returns warnings, not crash.

## Task 2.4: Add supplemental seed-source hints

Acceptance: high-evidence/high-citation works with PMID/DOI become supplemental `SeedSource` objects with provenance and no fabricated citation fields. They are merged with curated evidence-pack seeds by PMID/DOI/PMCID/work_id; corpus-derived duplicates add provenance but do not replace curated seed identity.

## Task 2.5: Add prior-target divergence reporting

Acceptance: when the local corpus contributes both prior terms and retrieval target records, the plan records `prior_target_divergence` metadata: prior sources, target sources, independent PubMed/allowlist corroboration counts, local-corpus-only records, and warnings/quarantine status. This check prevents a subject-normalization bug in the corpus from biasing both the query and the evidence target invisibly.

---

# Phase 3 task skeleton: PubMed/MCP search integration

Do not change public tool schemas without updating `tests/fixtures/contracts/mcp_tools.json`.

## Task 3.1: Add private structured PubMed search helper

**Files:**
- Modify: `caseprep/mcp_server.py`
- Test: new or existing MCP tests

Add private helper:

```python
async def _handle_pubmed_structured(args: dict) -> dict:
    ...
```

It should return original query, optional query plan, articles, evidence grades, and formatted markdown.

## Task 3.2: Add optional `retrieval_strategy` to `_handle_pubmed()`

Existing output remains markdown. Strategy values are `legacy`, `deterministic_enrichment`, `landmark_seeded`, `local_prior`, `hybrid`, and `shadow`; default is `legacy`. If `return_query_plan` is true, include a markdown query-plan section or return structured through web only. Preserve current tests.

## Task 3.3: Extend `/api/search` additively

**Files:**
- Modify: `caseprep/web.py`
- Test: `tests/test_web.py`

Add query params only if public route contract remains same:

```python
retrieval_strategy: str = Query("legacy")
return_query_plan: bool = Query(False)
```

Return old fields plus additive fields.

---

# Phase 4 task skeleton: Full-text retriever

## Task 4.1: Add `FullTextRecord` contract locally in retriever module

**Files:**
- Create: `caseprep/retrievers/fulltext.py`
- Create: `tests/test_fulltext_retriever.py`

Keep it internal until stable; do not change `core/contracts.py` prematurely.

## Task 4.2: Wrap existing PubMed/PMC helpers by injection

Constructor accepts functions for summaries, fulltext, structured abstracts, and plain abstracts so tests do not hit network.

## Task 4.3: Add local fulltext DB resolver

Use `_corpus_get_paper()` behavior as a reference, but put read-only fulltext resolution behind the retriever.

## Task 4.4: Make `_handle_get_fulltext()` a formatter wrapper

Preserve existing text output in tests while adding structured internals.

---

# Phase 5 task skeleton: Core builder integration

## Task 5.1: Store query enrichment under `structured["retrieval"]["query_enrichment"]`

Do this before changing actual retrieval calls.

## Task 5.2: Tag evidence with query IDs and matched concepts

Update `_tag_evidence()` or call sites to include merged metadata:

```python
metadata["query_ids"]
metadata["matched_axes"]
metadata["matched_concepts"]
metadata["expansion_provenance"]
```

If a record is retrieved by multiple axes, merge rather than overwrite these lists.

## Task 5.3: Replace corpus single-topic query with local corpus query object

Current code uses `provider_set.corpus.retrieve(topic, ...)`. Switch to the `local_corpus` query in the enriched plan when present.

## Task 5.4: Only then switch PubMed axes to enriched PubMed queries behind a flag

Use an environment flag or request option first:

```python
options={"retrieval_strategy": "hybrid"}
```

Do not flip default until canonical eval + blind clinical review pass.

## Task 5.5: Add explicit enriched-retrieval default-flip eval gate

Create a frozen eval fixture for the canonical M1 thrombectomy case and at least one non-thrombectomy case. Gate criteria:

- `Recall@20` against required landmark PMIDs meets the chosen threshold (document the threshold in the test fixture; start with `>= 0.8` for search-only and 100% for must-retrieve evidence-pack seeds that have identifiers).
- A separate retrieval-only check with the curated seed allowlist disabled still retrieves a reasonable subset of landmark papers, so the allowlist does not mask broken query construction.
- With allowlist enabled, every must-retrieve seed is either fetched into evidence or explicitly reported missing with PMID/DOI and error provenance.
- Dedup by PMID/DOI/PMCID/work_id/title preserves merged `query_ids`, axes, concepts, and provenance.
- Off-target/quarantined evidence rate is below the declared threshold.
- No literature-derived claim asserts patient laterality unless supported by case facts and query policy.
- Blind clinical review passes the stored rubric before `legacy` defaults can change.

---

# Phase 6 task skeleton: API transparency

## Task 6.1: Add adapter payload fields additively

**Files:**
- Modify: `caseprep/adapters/caseplan.py`
- Test: `tests/test_core_adapters.py`, `tests/test_web.py`

Add optional fields without removing `summary`.

## Task 6.2: Add dashboard-safe evidence summary

Do not dump full abstracts into dashboard history. Provide counts, IDs, source tiers, warnings, and artifact paths.

---

# Verification checklist

Before declaring the whole feature complete:

- [ ] Phase 1 pure seam passes targeted and full tests.
- [ ] No public MCP/FastAPI contracts changed accidentally.
- [ ] NSGY_DB adapter degrades cleanly when DBs are unavailable.
- [ ] PubMed/PMC calls still work without an NCBI API key.
- [ ] Laterality is preserved as a case fact; broad queries strip it through explicit `case_fact_policy`, and any laterality-sensitive query declares why it includes laterality.
- [ ] PubMed query strings use structured specs with MeSH terms, `[tiab]` field tags, date filters when appropriate, and no silent alias truncation.
- [ ] M1 thrombectomy enrichment includes population, temporal-window, and imaging-modality concepts.
- [ ] Landmark seed PMIDs/DOIs come from curated evidence packs independent of NSGY_DB and are deduped/merged with corpus-derived identifiers.
- [ ] Every expansion term, query, seed source, adapter warning, and final evidence record has provenance.
- [ ] Every final citable source becomes an `EvidenceRecord` with PMID/DOI/PMCID/work_id where available.
- [ ] Evidence dedupe merges query IDs, matched concepts, axes, and provenance instead of dropping retrieval context.
- [ ] Prior-target divergence is reported when local corpus supplies both priors and target records.
- [ ] Quarantined/off-target evidence is visible but excluded from deterministic synthesis.
- [ ] M1 thrombectomy canonical output improves or at least does not regress under deterministic eval.
- [ ] Landmark Recall@20 / seed-fetch / off-target thresholds pass before enriched retrieval becomes default.
- [ ] A blind clinical review is run before making enriched retrieval default.
