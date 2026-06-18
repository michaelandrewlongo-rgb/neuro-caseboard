"""Authored, cited prognostic-sign registry, keyed by procedure family.

Content is curated (like the decision/rescue tables), not per-case LLM output.
Each indicator cites stable evidence-pack item IDs so a clinician can trace it to
a landmark trial/guideline. Built family-agnostic: later cycles add families to
`_FAMILY_PROGNOSTIC_SIGNS` and the audit/render reuse this module unchanged.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from caseprep.evidence_packs.thrombectomy import THROMBECTOMY_PACKS

# Each entry: {"indicator": str, "detail": str, "source_ids": [pack_item_id, ...]}
_THROMBECTOMY_PROGNOSTIC_SIGNS: dict[str, list[dict[str, Any]]] = {
    "favorable": [
        {"indicator": "High ASPECTS (>=6)",
         "detail": "Limited early ischemic change predicts better EVT benefit.",
         "source_ids": ["hermes", "aha_asa_2019_update"]},
        {"indicator": "Good collaterals",
         "detail": "Robust pial collaterals sustain penumbra and improve outcome.",
         "source_ids": ["hermes"]},
        {"indicator": "Short onset-to-reperfusion time",
         "detail": "Faster reperfusion strongly increases the odds of independence.",
         "source_ids": ["hermes"]},
        {"indicator": "Successful reperfusion (mTICI 2b-3)",
         "detail": "Substantial/complete reperfusion is the dominant modifiable predictor.",
         "source_ids": ["hermes"]},
        {"indicator": "Late-window clinical-core mismatch met",
         "detail": "DAWN/DEFUSE-3 selection criteria identify late patients who still benefit.",
         "source_ids": ["dawn", "defuse_3"]},
        {"indicator": "Younger age / low baseline mRS",
         "detail": "Younger, independent patients have greater absolute benefit.",
         "source_ids": ["hermes"]},
    ],
    "unfavorable": [
        {"indicator": "Low ASPECTS / large ischemic core",
         "detail": "Large established core lowers benefit and raises hemorrhage risk; weigh large-core trial caveats.",
         "source_ids": ["select2", "hermes"]},
        {"indicator": "Poor collaterals",
         "detail": "Sparse collaterals accelerate core growth and worsen outcome.",
         "source_ids": ["hermes"]},
        {"indicator": "Long time-to-reperfusion",
         "detail": "Each hour of delay reduces the probability of functional independence.",
         "source_ids": ["hermes"]},
        {"indicator": "Failed / partial reperfusion (<mTICI 2b)",
         "detail": "Incomplete reperfusion predicts poor functional outcome.",
         "source_ids": ["hermes"]},
        {"indicator": "Late presentation without qualifying mismatch",
         "detail": "Outside DAWN/DEFUSE-3 selection, late EVT benefit is unproven.",
         "source_ids": ["dawn", "defuse_3"]},
    ],
}

_FAMILY_PROGNOSTIC_SIGNS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "endovascular_thrombectomy": _THROMBECTOMY_PROGNOSTIC_SIGNS,
}


def prognostic_signs_for_family(family_id: str) -> dict[str, list[dict[str, Any]]] | None:
    """Return the authored {favorable, unfavorable} block for a family, or None."""
    block = _FAMILY_PROGNOSTIC_SIGNS.get(family_id)
    if block is None:
        return None
    return {
        group: [dict(entry, source_ids=list(entry["source_ids"])) for entry in entries]
        for group, entries in block.items()
    }


@lru_cache(maxsize=None)
def _thrombectomy_item_index() -> dict[str, Any]:
    index: dict[str, Any] = {}
    for pack in THROMBECTOMY_PACKS.values():
        for item in pack.items:
            index[item.id] = item
    return index


def valid_thrombectomy_pack_ids() -> set[str]:
    """All item IDs declared across the thrombectomy evidence packs."""
    return set(_thrombectomy_item_index().keys())


def resolve_pack_refs(source_ids: list[str]) -> str:
    """Human-readable citation string, e.g. 'hermes (PMID 26898852); dawn (PMID 29129157)'."""
    index = _thrombectomy_item_index()
    parts: list[str] = []
    for sid in source_ids:
        item = index.get(sid)
        if item is None:
            parts.append(sid)
            continue
        ref_bits = []
        if item.pmid:
            ref_bits.append(f"PMID {item.pmid}")
        elif item.doi:
            ref_bits.append(f"DOI {item.doi}")
        parts.append(f"{sid} ({'; '.join(ref_bits)})" if ref_bits else sid)
    return "; ".join(parts)
