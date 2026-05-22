"""Deterministic query enrichment between parsed cases and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from caseprep.case_parser import CaseSpec
from caseprep.profile_classifier import ProfileName
from caseprep.procedure_taxonomy import ProcedureFamily

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
    "deterministic_enrichment",
    "landmark_seeded",
    "local_prior",
    "hybrid",
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

_DEFAULT_PUBLICATION_FILTER = "2015/01/01:3000/12/31"


@dataclass(frozen=True)
class ExpansionProvenance:
    """Single provenance atom for an expansion term or query seed."""

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
    """Expanded term used by deterministic query building."""

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


@dataclass(frozen=True)
class SeedSource:
    """A single deterministic seed that should be attempted as evidence target."""

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
class PubMedQuerySpec:
    """Structured query representation for PubMed rendering and auditing."""

    mesh_terms: tuple[str, ...] = ()
    tiab_terms: tuple[str, ...] = ()
    date_filter: str | None = None
    included_terms: tuple[str, ...] = ()
    omitted_terms: tuple[str, ...] = ()

    def render(self) -> str:
        groups: list[str] = []
        if self.mesh_terms:
            groups.append(_fielded_or(self.mesh_terms, "mesh"))
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
    """Per-query case-fact handling policy."""

    laterality: LateralityPolicy = "not_applicable"
    rationale: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "laterality": self.laterality,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class RetrievalQuery:
    """A retrieval request emitted by the deterministic enrichment seam."""

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
            "query_spec": self.query_spec.to_dict() if self.query_spec is not None else None,
            "case_fact_policy": self.case_fact_policy.to_dict(),
            "purpose": self.purpose,
            "axis": self.axis,
            "identifiers": list(self.identifiers),
            "provenance": [item.to_dict() for item in self.provenance],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PriorEnrichment:
    """Structured prior returned by adapter or fallback source."""

    expansion_terms: tuple[ExpansionTerm, ...] = ()
    seed_sources: tuple[SeedSource, ...] = ()
    subdomain_hints: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    quarantined_terms: tuple[ExpansionTerm, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expansion_terms": [term.to_dict() for term in self.expansion_terms],
            "seed_sources": [seed.to_dict() for seed in self.seed_sources],
            "subdomain_hints": list(self.subdomain_hints),
            "warnings": list(self.warnings),
            "quarantined_terms": [term.to_dict() for term in self.quarantined_terms],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EnrichedRetrievalPlan:
    """Transport-neutral, JSON-serializable retrieval enrichment plan."""

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
    """Adapter seam for local corpus priors (Phase 2+ actual implementation)."""

    def enrich(
        self,
        case: CaseSpec,
        family: ProcedureFamily | None,
        profile: ProfileName,
    ) -> PriorEnrichment:
        ...


class LandmarkSeedProvider(Protocol):
    """Adapter seam for explicit seed provision beyond defaults."""

    def seed_sources(
        self,
        case: CaseSpec,
        family: ProcedureFamily | None,
        profile: ProfileName,
    ) -> list[SeedSource]:
        ...


def _fielded_term(term: str, field: str) -> str:
    escaped = term.replace('"', '\\"')
    needs_quotes = any(char.isspace() for char in escaped) or "-" in escaped or "/" in escaped
    if needs_quotes:
        return f'"{escaped}"[{field}]'
    return f"{escaped}[{field}]"


def _fielded_or(terms: tuple[str, ...], field: str) -> str:
    if not terms:
        return ""
    if len(terms) == 1:
        return _fielded_term(terms[0], field)
    return "(" + " OR ".join(_fielded_term(term, field) for term in terms) + ")"


def _date_filter_clause(date_filter: str) -> str:
    start, end = date_filter.split(":", 1)
    return f'("{start}"[Date - Publication] : "{end}"[Date - Publication])'


_THROMBECTOMY_TERMS: tuple[ExpansionTerm, ...] = (
    ExpansionTerm(
        canonical="M1 occlusion",
        aliases=(
            "M1 occlusion",
            "middle cerebral artery occlusion",
            "MCA occlusion",
            "large vessel occlusion",
            "anterior circulation LVO",
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
            "mTICI",
            "modified Rankin Scale",
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
            "ASPECTS",
            "MRI selection",
            "perfusion imaging",
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


def _bounded_aliases(
    aliases: list[str], *, limit: int = 24
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    included = tuple(aliases[:limit])
    omitted = tuple(aliases[limit:])
    return included, omitted


def _broad_literature_policy(case: CaseSpec) -> CaseFactPolicy:
    if case.laterality.value:
        return CaseFactPolicy(
            laterality="strip_for_broad_literature_search",
            rationale=(
                "Broad evidence/outcome retrieval is not right/left specific; "
                "laterality remains in CaseSpec."
            ),
        )
    return CaseFactPolicy(laterality="not_applicable", rationale="")


def _seed_identities(seed: SeedSource) -> tuple[tuple[str, str], ...]:
    identities: list[tuple[str, str]] = []
    for field in ("pmid", "doi", "pmcid", "work_id"):
        value = getattr(seed, field)
        if value:
            identities.append((field, value.strip().casefold()))
    return tuple(identities)


def _seed_identity(seed: SeedSource) -> tuple[str, str] | None:
    identities = _seed_identities(seed)
    return identities[0] if identities else None


def _combine_seed_sources(primary: SeedSource, secondary: SeedSource) -> SeedSource:
    return SeedSource(
        id=primary.id,
        title_hint=primary.title_hint or secondary.title_hint,
        pmid=primary.pmid or secondary.pmid,
        doi=primary.doi or secondary.doi,
        pmcid=primary.pmcid or secondary.pmcid,
        work_id=primary.work_id or secondary.work_id,
        tier=primary.tier or secondary.tier,
        conditional=primary.conditional or secondary.conditional,
        provenance=primary.provenance + secondary.provenance,
    )


def _rebuild_seed_identity_index(seeds: list[SeedSource]) -> dict[tuple[str, str], int]:
    index: dict[tuple[str, str], int] = {}
    for seed_index, seed in enumerate(seeds):
        for key in _seed_identities(seed):
            index[key] = seed_index
    return index


def _merge_seed_sources(*groups: tuple[SeedSource, ...]) -> tuple[SeedSource, ...]:
    merged: list[SeedSource] = []
    index: dict[tuple[str, str], int] = {}
    for group in groups:
        for seed in group:
            keys = _seed_identities(seed)
            existing_indexes = sorted({index[key] for key in keys if key in index})
            if not keys or not existing_indexes:
                for key in keys:
                    index[key] = len(merged)
                merged.append(seed)
                continue

            merge_index = existing_indexes[0]
            coalesced_keys = set(keys)
            merged_seed = merged[merge_index]
            coalesced_keys.update(_seed_identities(merged_seed))
            for duplicate_index in existing_indexes[1:]:
                coalesced_keys.update(_seed_identities(merged[duplicate_index]))
                merged_seed = _combine_seed_sources(merged_seed, merged[duplicate_index])
            merged_seed = _combine_seed_sources(merged_seed, seed)
            coalesced_keys.update(_seed_identities(merged_seed))

            if len(existing_indexes) == 1:
                merged[merge_index] = merged_seed
                for key in coalesced_keys:
                    index[key] = merge_index
                continue

            duplicate_indexes = set(existing_indexes[1:])
            coalesced: list[SeedSource] = []
            for current_index, current_seed in enumerate(merged):
                if current_index == merge_index:
                    coalesced.append(merged_seed)
                elif current_index not in duplicate_indexes:
                    coalesced.append(current_seed)
            merged = coalesced
            index = _rebuild_seed_identity_index(merged)
            for key in coalesced_keys:
                index[key] = merge_index
    return tuple(merged)


def _thrombectomy_evidence_pack_seeds(
    case: CaseSpec,
    family: ProcedureFamily | None,
    profile: ProfileName,
) -> tuple[SeedSource, ...]:
    from caseprep.evidence_packs.thrombectomy import ANTERIOR_CIRCULATION_LVO_M1

    if family is None or getattr(family, "id", None) != "endovascular_thrombectomy":
        return ()

    provenance = ExpansionProvenance(
        source="caseprep.evidence_packs.thrombectomy",
        field_path="ANTERIOR_CIRCULATION_LVO_M1.items",
        matched_value="endovascular_thrombectomy",
    )

    seeds: list[SeedSource] = []
    for item in ANTERIOR_CIRCULATION_LVO_M1.items:
        if not item.pmid and not item.doi:
            continue
        seeds.append(
            SeedSource(
                id=item.id,
                title_hint=item.title_hint,
                pmid=item.pmid,
                doi=item.doi,
                tier=item.tier,
                conditional=item.conditional,
                provenance=(provenance,),
            )
        )
    return tuple(seeds)


def _case_text_query(raw_text: str) -> PubMedQuerySpec:
    return PubMedQuerySpec(
        tiab_terms=(raw_text,),
        included_terms=(raw_text,),
    )


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
    prior_adapter: NeurosurgeryPriorAdapter | None = None,
    seed_provider: LandmarkSeedProvider | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable enriched retrieval plan.

    The enrichment layer can suggest search terms and seed identifiers but must not
    mutate or overwrite parser-derived CaseSpec facts.
    """

    validated_profile = _validate_profile(profile)

    procedure_family = family.id if family is not None and hasattr(family, "id") else case.procedure_family.value

    baseline_provenance = ExpansionProvenance(
        source="case_parser",
        field_path="case.raw_input",
        matched_value=case.raw_input,
        notes="baseline query from parsed case text",
    )

    terms: list[ExpansionTerm] = [
        ExpansionTerm(
            canonical=case.raw_input,
            aliases=(case.raw_input,),
            concept_type="pathology",
            confidence=0.5,
            provenance=(baseline_provenance,),
        )
    ]

    prior = PriorEnrichment()
    active_prior_adapter = neurosurgery_adapter or prior_adapter
    if active_prior_adapter is not None and retrieval_strategy in _LOCAL_PRIOR_STRATEGIES:
        prior = active_prior_adapter.enrich(case, family, validated_profile)
        terms.extend(prior.expansion_terms)

    if (
        procedure_family == "endovascular_thrombectomy"
        and not case.degraded
        and retrieval_strategy in _LOCAL_PRIOR_STRATEGIES | {"deterministic_enrichment", "landmark_seeded"}
    ):
        terms.extend(_THROMBECTOMY_TERMS)

    warnings: list[str] = list(prior.warnings)
    if case.degraded:
        warnings.append(
            "Using generic baseline query because the case is degraded or lacks a "
            "supported high-confidence procedure family."
        )

    evidence_pack_seeds = _thrombectomy_evidence_pack_seeds(case, family, validated_profile)
    explicit_seed_sources = tuple(seed_provider.seed_sources(case, family, validated_profile)) if seed_provider else ()
    seed_sources = _merge_seed_sources(evidence_pack_seeds, explicit_seed_sources, prior.seed_sources)

    baseline_spec = _case_text_query(case.raw_input)

    if procedure_family == "endovascular_thrombectomy" and not case.degraded:
        anatomy_aliases = _aliases_for_type(terms, "anatomy")
        procedure_aliases = _aliases_for_type(terms, "procedure")
        outcome_aliases = _aliases_for_type(terms, "outcome")
        population_aliases = _aliases_for_type(terms, "population")
        temporal_aliases = _aliases_for_type(terms, "temporal_window")
        imaging_aliases = _aliases_for_type(terms, "imaging_modality")

        broad_terms = (
            list(procedure_aliases)
            + list(anatomy_aliases)
            + list(outcome_aliases)
            + list(population_aliases)
            + list(temporal_aliases)
            + list(imaging_aliases)
        )
        alias_limit = 40 if retrieval_strategy not in _LOCAL_PRIOR_STRATEGIES else 24
        included, omitted = _bounded_aliases(broad_terms, limit=alias_limit)

        outcomes_warnings = ()
        if omitted:
            outcomes_warnings = (
                f"PubMed query omitted {len(omitted)} bounded aliases; "
                "see query_spec.omitted_terms."
            ,)
            warnings.extend(outcomes_warnings)

        outcomes_spec = PubMedQuerySpec(
            mesh_terms=("Stroke", "Thrombectomy", "Middle Cerebral Artery", "Treatment Outcome"),
            tiab_terms=included,
            date_filter=_DEFAULT_PUBLICATION_FILTER,
            included_terms=included,
            omitted_terms=omitted,
        )

        technique_spec = PubMedQuerySpec(
            mesh_terms=("Thrombectomy", "Middle Cerebral Artery"),
            tiab_terms=tuple(
                procedure_aliases
                + anatomy_aliases
                + ["technique", "device", "stent retriever"]
            ),
            date_filter=_DEFAULT_PUBLICATION_FILTER,
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
                provenance=(baseline_provenance,),
                warnings=outcomes_warnings,
            ),
            RetrievalQuery(
                id="pubmed_technique",
                label="Surgical Technique",
                retriever="pubmed",
                query_spec=technique_spec,
                purpose="broad procedure-specific technique retrieval",
                axis="technique",
                case_fact_policy=_broad_literature_policy(case),
                provenance=(baseline_provenance,),
            ),
            RetrievalQuery(
                id="local_corpus_prior",
                label="Local Corpus Prior",
                retriever="local_corpus",
                query="mechanical thrombectomy M1 MCA large vessel occlusion",
                purpose=(
                    "local neurosurgery corpus target retrieval; do not treat "
                    "as independent of the corpus prior"
                ),
                axis="prior",
                case_fact_policy=_broad_literature_policy(case),
                provenance=(baseline_provenance,),
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
                provenance=(baseline_provenance,),
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
