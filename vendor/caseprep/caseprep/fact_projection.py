"""Helpers for rendering structured case facts into human-readable lines."""

from __future__ import annotations

from typing import Any, Mapping

from caseprep.facts import FactStatus

_MISSING_TEXT = "missing/needs input"


def has_known_fact(facts: Mapping[str, Mapping[str, Any]], key: str) -> bool:
    """Return True when a fact is present, known, and non-empty."""
    fact = _fact(facts, key)
    return fact.get("status") == FactStatus.KNOWN.value and bool(fact.get("value"))


def fact_line(facts: Mapping[str, Mapping[str, Any]], key: str, *, label: str | None = None) -> str:
    """Render a simple fact line with a missing placeholder when unknown."""
    fact = _fact(facts, key)
    rendered_label = label or str(fact.get("label") or _fallback_label(key))
    value = fact.get("value")
    if fact.get("status") == FactStatus.KNOWN.value and value:
        return f"{rendered_label}: {value}"
    return f"{rendered_label}: {_MISSING_TEXT}"


def missing_or_confirm_line(
    facts: Mapping[str, Mapping[str, Any]],
    key: str,
    *,
    label: str | None = None,
) -> str:
    """Render known, confirm, or missing state for a fact."""
    fact = _fact(facts, key)
    rendered_label = label or str(fact.get("label") or _fallback_label(key))
    value = fact.get("value")
    if fact.get("status") == FactStatus.KNOWN.value and value:
        return f"{rendered_label}: {value}"
    if fact.get("status") == FactStatus.CONFIRM.value and value:
        return f"{rendered_label}: confirm {value}"
    return f"{rendered_label}: {_MISSING_TEXT}"


def _fact(facts: Mapping[str, Mapping[str, Any]], key: str) -> Mapping[str, Any]:
    fact = facts.get(key)
    return fact if isinstance(fact, Mapping) else {}


def _fallback_label(key: str) -> str:
    return key.replace("_", " ").capitalize()
