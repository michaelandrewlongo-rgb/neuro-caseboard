"""Deterministic fallback intent classification for CasePrep requests.

This module deliberately classifies and plans output shape only. It must not
answer clinical questions or generate unsupported clinical conclusions.
"""

from __future__ import annotations

import re

from caseprep.core.contracts import OutputIntentPlan

_OPERATIVE_SECTIONS = [
    "case_frame",
    "positioning_and_setup",
    "approach_and_exposure",
    "anatomy_at_risk",
    "key_steps",
    "complication_avoidance",
    "evidence_appendix",
]

_LITERATURE_SECTIONS = [
    "clinical_question",
    "search_strategy",
    "best_available_evidence",
    "outcome_or_rate_synthesis",
    "limitations",
    "bottom_line_with_citations",
]

_OPERATIVE_PRIORITIES = [
    "anatomy",
    "technique",
    "approach",
    "complications",
    "reviews_landmarks",
]

_LITERATURE_PRIORITIES = [
    "clinical_question",
    "outcomes",
    "incidence_rates",
    "risk_factors",
    "systematic_reviews_meta_analyses",
]


def _contains_word(query: str, term: str) -> bool:
    """Return true when a term appears as a phrase/word, not as a substring."""
    escaped = re.escape(term)
    return re.search(rf"(?<!\w){escaped}(?!\w)", query) is not None


def _literature_subtype(query: str) -> str:
    if any(_contains_word(query, term) for term in ("vs", "versus", "compared")):
        return "comparative_outcomes"
    if any(term in query for term in ("outcome", "outcomes")):
        return "comparative_outcomes"
    if any(term in query for term in ("incidence", "rate", "rates")):
        return "incidence"
    if "risk factor" in query or "risk factors" in query:
        return "risk_factors"
    if "prognosis" in query or "prognostic" in query:
        return "prognosis"
    return "general_evidence_summary"


def _operative_subtype(query: str) -> str:
    if any(term in query for term in ("approach", "exposure", "retrosig")):
        return "approach"
    if any(term in query for term in ("technique", "steps", "resection", "clipping", "fusion")):
        return "technique"
    if any(term in query for term in ("positioning", "setup")):
        return "perioperative_setup"
    if "anatomy" in query:
        return "anatomy_at_risk"
    if "complication" in query or "avoidance" in query:
        return "complication_avoidance"
    return "case_prep"


def heuristic_intent_plan(query: str) -> OutputIntentPlan:
    """Classify a CasePrep request into an output family and planning labels.

    The fallback favors operative briefings for ambiguous neurosurgical prompts
    because the core product is case preparation; it adds an explicit warning
    when no routing keywords are detected.
    """
    normalized_query = " ".join((query or "").strip().lower().split())
    warnings: list[str] = []

    literature_terms = (
        "versus",
        "compared",
        "outcome",
        "outcomes",
        "incidence",
        "rate",
        "rates",
        "risk factor",
        "risk factors",
        "prognosis",
        "prognostic",
        "meta-analysis",
        "systematic review",
    )
    is_literature = _contains_word(normalized_query, "vs") or any(
        term in normalized_query for term in literature_terms
    )

    operative_terms = (
        "approach",
        "technique",
        "steps",
        "exposure",
        "positioning",
        "operative",
        "case",
        "resection",
        "clipping",
        "fusion",
        "retrosig",
    )
    is_operative = any(term in normalized_query for term in operative_terms)

    if is_literature:
        return OutputIntentPlan(
            intent_type="literature_review",
            subtype=_literature_subtype(normalized_query),
            confidence=0.85,
            normalized_query=normalized_query,
            template_sections=list(_LITERATURE_SECTIONS),
            retrieval_priorities=list(_LITERATURE_PRIORITIES),
            source="heuristic_fallback",
        )

    if not is_operative:
        warnings.append("defaulted_to_operative_briefing")

    return OutputIntentPlan(
        intent_type="operative_briefing",
        subtype=_operative_subtype(normalized_query),
        confidence=0.75 if warnings else 0.85,
        normalized_query=normalized_query,
        template_sections=list(_OPERATIVE_SECTIONS),
        retrieval_priorities=list(_OPERATIVE_PRIORITIES),
        warnings=warnings,
        source="heuristic_fallback",
    )
