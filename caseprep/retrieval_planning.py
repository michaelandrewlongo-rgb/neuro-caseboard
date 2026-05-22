"""Procedure-aware retrieval query planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re

from caseprep.case_parser import CaseSpec
from caseprep.evidence_packs.thrombectomy import resolve_thrombectomy_pack
from caseprep.procedure_taxonomy import ProcedureFamily
from caseprep.profile_classifier import ProfileName, build_keywords, classify_profile
from caseprep.query_enrichment import RetrievalStrategy


@dataclass(frozen=True)
class RetrievalAxis:
    id: str
    label: str
    query: str
    filter_type: str | None = None


_CORPUS_QUERY_TERMS: Mapping[str, tuple[str, ...]] = {
    "spine_acdf": (
        "ACDF",
        "anterior cervical",
        "discectomy",
        "fusion",
        "radiculopathy",
        "foraminotomy",
        "uncinate",
    ),
    "tumor_convexity_meningioma": (
        "meningioma",
        "convexity",
        "parasagittal",
        "superior sagittal sinus",
        "bridging veins",
        "Simpson",
        "venous infarct",
    ),
    "posterior_fossa_chiari": (
        "Chiari",
        "syringomyelia",
        "posterior fossa decompression",
        "suboccipital decompression",
        "C1",
        "duraplasty",
        "foramen magnum",
    ),
    "endovascular_thrombectomy": (
        "mechanical thrombectomy",
        "endovascular thrombectomy",
        "M1",
        "MCA",
        "middle cerebral artery",
        "large vessel occlusion",
        "stent retriever",
        "aspiration",
        "TICI",
        "mTICI",
        "first pass",
    ),
}


def resolve_case_evidence_pack(
    case: CaseSpec,
    family: ProcedureFamily | None,
) -> str | None:
    """Return a deterministic evidence-pack ID for specific structured cases."""
    if family is None or family.id != "endovascular_thrombectomy":
        return None
    pack = resolve_thrombectomy_pack(case)
    return pack.id if pack is not None else None


def build_case_queries(
    case: CaseSpec,
    family: ProcedureFamily | None,
) -> list[RetrievalAxis]:
    """Build PubMed/corpus query axes from structured case fields."""
    topic = case.raw_input.strip()
    if family is not None:
        templates = family.retrieval_templates
        review_subject = _review_subject(case, family)
        return [
            RetrievalAxis(
                id="anatomy",
                label="Anatomy / Relevant Structures",
                query=_template_query(templates, "anatomy", topic),
            ),
            RetrievalAxis(
                id="outcomes",
                label="Outcomes / Evidence",
                query=_template_query(templates, "outcomes", f"{topic} outcomes"),
                filter_type="therapy",
            ),
            RetrievalAxis(
                id="technique",
                label="Surgical Technique",
                query=_template_query(
                    templates,
                    "technique",
                    f"{topic} surgical technique approach",
                ),
            ),
            RetrievalAxis(
                id="complications",
                label="Complications",
                query=_template_query(
                    templates,
                    "complications",
                    f"{topic} complications adverse",
                ),
                filter_type="etiology",
            ),
            RetrievalAxis(
                id="reviews",
                label="Reviews / Landmarks",
                query=templates.get("reviews") or f"{review_subject} systematic review",
                filter_type="systematic_review",
            ),
        ]

    profile = case.broad_profile.value or classify_profile(topic).profile
    profile_keywords = build_keywords(profile)
    anatomy_query = _build_enriched_query(topic, profile_keywords["anatomy"][:5])
    return [
        RetrievalAxis(
            id="anatomy",
            label="Anatomy / Relevant Structures",
            query=anatomy_query,
        ),
        RetrievalAxis(
            id="outcomes",
            label="Outcomes / Evidence",
            query=f"{topic} outcomes",
            filter_type="therapy",
        ),
        RetrievalAxis(
            id="technique",
            label="Surgical Technique",
            query=f"{topic} surgical technique approach",
        ),
        RetrievalAxis(
            id="complications",
            label="Complications",
            query=f"{topic} complications adverse",
            filter_type="etiology",
        ),
        RetrievalAxis(
            id="reviews",
            label="Reviews / Landmarks",
            query=topic,
            filter_type="systematic_review",
        ),
    ]


def build_enriched_retrieval_plan(
    case: CaseSpec,
    family: ProcedureFamily | None,
    *,
    profile: ProfileName,
    retrieval_strategy: RetrievalStrategy = "deterministic_enrichment",
    neurosurgery_adapter=None,
    seed_provider=None,
) -> dict:
    """Build an auditable enriched retrieval plan without changing legacy axes."""
    from caseprep.query_enrichment import enrich_case_query

    return enrich_case_query(
        case,
        family,
        profile=profile,
        retrieval_strategy=retrieval_strategy,
        neurosurgery_adapter=neurosurgery_adapter,
        seed_provider=seed_provider,
    )


def build_corpus_query(
    case: CaseSpec,
    family: ProcedureFamily | None,
) -> str:
    """Render a deterministic FTS5-safe local-corpus query.

    FTS5 treats whitespace as a strict conjunction, so whole free-text case
    strings are brittle. This renderer keeps canonical parser facts intact but
    turns procedure-family concepts into a bounded OR query with quoted phrases.
    """
    if family is None:
        return case.raw_input.strip()

    terms: list[str] = []
    terms.extend(_case_specific_corpus_terms(case))
    terms.extend(_CORPUS_QUERY_TERMS.get(family.id, ()))
    if not terms:
        terms.append(family.display_name)
    return _render_fts5_or_query(terms)


def _template_query(
    templates: Mapping[str, str],
    key: str,
    fallback: str,
) -> str:
    value = templates.get(key)
    if value:
        return value
    return fallback


def _review_subject(case: CaseSpec, family: ProcedureFamily) -> str:
    parts: list[str] = []
    for field in (case.procedure, case.pathology):
        if field.value:
            parts.append(field.value)
    if not parts:
        parts.append(family.display_name)
    return " ".join(_unique(parts))


def _build_enriched_query(topic: str, terms: list[str]) -> str:
    parts = [topic]
    seen = {topic.lower()}
    for term in terms:
        normalized = term.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(normalized)

    query = " ".join(parts)
    if len(query) > 200:
        query = query[:200].rsplit(" ", 1)[0]
    return query


def _case_specific_corpus_terms(case: CaseSpec) -> list[str]:
    terms: list[str] = []
    for field in (
        case.level_or_segment,
        case.pathology,
        case.procedure,
        case.approach,
        case.anatomic_location,
    ):
        if not field.value:
            continue
        terms.extend(_split_case_field_terms(field.value))
    return terms


def _split_case_field_terms(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*;\s*", value) if part.strip()]


def _render_fts5_or_query(terms: tuple[str, ...] | list[str]) -> str:
    formatted_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        formatted = _format_fts5_term(term)
        if not formatted:
            continue
        key = formatted.casefold()
        if key in seen:
            continue
        seen.add(key)
        formatted_terms.append(formatted)
    return " OR ".join(formatted_terms)


def _format_fts5_term(term: str) -> str:
    normalized = " ".join(term.strip().strip('"').split())
    if not normalized:
        return ""
    escaped = normalized.replace('"', " ").strip()
    if not escaped:
        return ""
    if re.search(r"[\s\-/]", escaped):
        return f'"{escaped}"'
    return escaped


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items
