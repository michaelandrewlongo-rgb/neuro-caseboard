"""Structured case facts used by parsers and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class FactStatus(str, Enum):
    """State of a case-specific fact."""

    KNOWN = "known"
    MISSING = "missing"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class CaseFact:
    """A deterministic fact extracted from, or requested for, a case prompt."""

    key: str
    label: str
    value: str | None = None
    status: FactStatus = FactStatus.MISSING
    source: str = "missing"
    confidence: float = 0.0
    span: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "status": self.status.value,
            "source": self.source,
            "confidence": self.confidence,
            "span": self.span,
            "notes": self.notes,
        }


def facts_to_dict(
    facts: Iterable[CaseFact | Mapping[str, Any]] | Mapping[str, CaseFact | Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Serialize facts into a stable key-indexed dictionary."""
    if isinstance(facts, Mapping):
        iterable = facts.items()
    else:
        iterable = ((None, fact) for fact in facts)

    serialized: dict[str, dict[str, Any]] = {}
    for outer_key, fact in iterable:
        item = _fact_as_dict(fact)
        key = item.get("key")
        if not key and outer_key is not None:
            key = outer_key
        if key is not None and str(key):
            if not item.get("key"):
                item["key"] = str(key)
            serialized[str(key)] = item
    return serialized


def fact_value(
    facts: Iterable[CaseFact | Mapping[str, Any]] | Mapping[str, CaseFact | Mapping[str, Any]],
    key: str,
) -> str | None:
    """Return a known fact value by key, otherwise None."""
    fact = facts_to_dict(facts).get(key)
    if not fact:
        return None
    if fact.get("status") != FactStatus.KNOWN.value:
        return None
    value = fact.get("value")
    return str(value) if value is not None else None


def _fact_as_dict(fact: CaseFact | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(fact, CaseFact):
        return fact.to_dict()
    item = dict(fact)
    status = item.get("status")
    if isinstance(status, FactStatus):
        item["status"] = status.value
    return item
