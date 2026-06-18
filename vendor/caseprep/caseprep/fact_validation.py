"""Non-fatal rendered fact consistency checks."""

from __future__ import annotations

from typing import Any, Mapping


_FACT_MISSING_PHRASES: dict[str, tuple[str, ...]] = {
    "nihss": (
        "NIHSS: missing/needs input",
        "NIHSS: incomplete/needs input",
        "NIHSS/disabling deficit: incomplete/needs input",
        "NIHSS/disabling deficit | incomplete/needs input",
    ),
    "aspects": (
        "ASPECTS: missing/needs input",
        "ASPECTS: incomplete/needs input",
        "ASPECTS/core: incomplete/needs input",
        "ASPECTS/core | incomplete/needs input",
        "ASPECTS numeric score and involved regions: incomplete/needs input",
    ),
    "last_known_well": (
        "Last known well: missing/needs input",
        "Last known well: incomplete/needs input",
        "Last-known-well/time window: incomplete/needs input",
        "Last-known-well/time window | incomplete/needs input",
        "LKW/time window: incomplete/needs input",
        "LKW/time window | incomplete/needs input",
    ),
    "access_route": (
        "Access route: missing/needs input",
        "Access route: incomplete/needs input",
        "Access plan: incomplete/needs input",
        "Access plan | incomplete/needs input",
    ),
    "perfusion_selection": (
        "Perfusion selection: missing/needs input",
        "Perfusion selection: incomplete/needs input",
        "Imaging selection: incomplete/needs input",
        "CTP/core-penumbra if late/unknown window: document ischemic core volume, penumbra/hypoperfusion volume, mismatch ratio, and whether profile supports EVT; patient-specific values incomplete/need input",
        "Core volume (mL), penumbra/hypoperfusion volume (mL), mismatch ratio, and Tmax/CBF thresholds if CTP used: incomplete/needs input",
    ),
}


def validate_rendered_fact_consistency(schema: Mapping[str, Any], markdown: str) -> list[str]:
    """Return warnings when known structured facts are rendered as missing.

    This validator is intentionally non-fatal. It only checks a small set of
    high-value thrombectomy fact states where stale generic placeholders have
    previously contradicted supplied structured facts.
    """
    facts = _case_facts(schema)
    warnings: list[str] = []
    for key, phrases in _FACT_MISSING_PHRASES.items():
        fact = facts.get(key)
        if not isinstance(fact, Mapping) or not _is_known_fact(fact):
            continue
        label = str(fact.get("label") or _fallback_label(key))
        value = str(fact.get("value"))
        for phrase in phrases:
            if _contains_phrase(markdown, phrase):
                warnings.append(
                    "Fact consistency warning: "
                    f"known {label} ({value}) rendered with missing phrase '{phrase}'"
                )
    return warnings


def _case_facts(schema: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    case_section = schema.get("case")
    if not isinstance(case_section, Mapping):
        return {}
    facts = case_section.get("facts")
    if not isinstance(facts, Mapping):
        return {}
    return {
        str(key): value
        for key, value in facts.items()
        if isinstance(value, Mapping)
    }


def _is_known_fact(fact: Mapping[str, Any] | None) -> bool:
    if not isinstance(fact, Mapping):
        return False
    return fact.get("status") == "known" and bool(fact.get("value"))


def _contains_phrase(markdown: str, phrase: str) -> bool:
    if phrase in markdown:
        return True
    if phrase.endswith("."):
        return phrase[:-1] in markdown
    return f"{phrase}." in markdown


def _fallback_label(key: str) -> str:
    return key.replace("_", " ").capitalize()
