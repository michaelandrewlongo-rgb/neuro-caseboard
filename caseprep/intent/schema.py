"""Validation for LLM intent-structurer payloads.

The intent schema is intentionally narrow: it may describe routing, labels, and
retrieval priorities, but it may not contain clinical conclusions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from caseprep.core import CasePrepValidationError, OutputIntentPlan

_ALLOWED_INTENTS = {"operative_briefing", "literature_review"}
_ALLOWED_SOURCES = {"llm", "heuristic_fallback", "explicit"}
_ANSWER_LANGUAGE = (
    "therefore",
    "superior",
    "inferior",
    "better",
    "worse",
    "recommended",
    "recommend",
    "choose",
    "preferred",
    "lower morbidity",
    "higher morbidity",
)
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")
_SENTENCE_PUNCT_RE = re.compile(r"[.!?]")


def _validation_error(message: str, field: str) -> CasePrepValidationError:
    return CasePrepValidationError(message, details={"field": field})


def _optional_str(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _validation_error(f"{field} must be a string or null", field)
    return value.strip() or None


def _str_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _validation_error(f"{field} must be a list of labels", field)
    labels: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise _validation_error(f"{field} entries must be strings", field)
        label = item.strip()
        if not label:
            continue
        _reject_answer_language(label, field=field)
        labels.append(label)
    return labels


def _reject_answer_language(text: str, *, field: str) -> None:
    lowered = text.lower()
    if any(token in lowered for token in _ANSWER_LANGUAGE):
        raise _validation_error(
            f"{field} may contain labels only, not clinical answer language",
            field,
        )
    if _PERCENT_RE.search(text):
        raise _validation_error(
            f"{field} may not contain rates or percentages",
            field,
        )
    # Labels should be compact section names/priorities, not prose sentences.
    if len(text) > 80 or _SENTENCE_PUNCT_RE.search(text):
        raise _validation_error(f"{field} entries must be compact labels", field)


def validate_intent_payload(
    payload: Mapping[str, Any],
    *,
    source: Literal["llm", "heuristic_fallback", "explicit"] = "llm",
) -> OutputIntentPlan:
    """Validate a raw intent payload and return an OutputIntentPlan.

    This function accepts only structured routing/planning fields. It rejects
    attempts to smuggle clinical conclusions into template labels or retrieval
    priorities.
    """
    if not isinstance(payload, Mapping):
        raise _validation_error("intent payload must be an object", "intent_payload")

    intent_type = payload.get("intent_type")
    if intent_type not in _ALLOWED_INTENTS:
        raise _validation_error(
            "intent_type must be operative_briefing or literature_review",
            "intent_type",
        )

    subtype = payload.get("subtype", "general")
    if not isinstance(subtype, str) or not subtype.strip():
        raise _validation_error("subtype must be a non-empty string", "subtype")

    confidence = payload.get("confidence", 1.0)
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise _validation_error("confidence must be numeric", "confidence")
    confidence = float(confidence)
    if confidence < 0.0 or confidence > 1.0:
        raise _validation_error("confidence must be between 0.0 and 1.0", "confidence")

    normalized_query = payload.get("normalized_query", "")
    if normalized_query is None:
        normalized_query = ""
    if not isinstance(normalized_query, str):
        raise _validation_error("normalized_query must be a string", "normalized_query")

    entities = payload.get("entities", {}) or {}
    if not isinstance(entities, Mapping):
        raise _validation_error("entities must be an object", "entities")

    clarification_needed = payload.get("clarification_needed", False)
    if not isinstance(clarification_needed, bool):
        raise _validation_error("clarification_needed must be boolean", "clarification_needed")

    requested_source = payload.get("source", source)
    if requested_source not in _ALLOWED_SOURCES:
        raise _validation_error("source is not allowed", "source")

    return OutputIntentPlan(
        intent_type=intent_type,  # type: ignore[arg-type]
        subtype=subtype.strip(),
        confidence=confidence,
        normalized_query=normalized_query.strip(),
        entities=dict(entities),
        template_sections=_str_list(payload.get("template_sections"), field="template_sections"),
        retrieval_priorities=_str_list(
            payload.get("retrieval_priorities"),
            field="retrieval_priorities",
        ),
        clarification_needed=clarification_needed,
        clarification_question=_optional_str(
            payload.get("clarification_question"),
            field="clarification_question",
        ),
        warnings=_str_list(payload.get("warnings"), field="warnings"),
        source=requested_source,  # type: ignore[arg-type]
    )
