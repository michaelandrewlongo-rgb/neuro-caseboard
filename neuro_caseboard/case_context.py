"""The structured case-intake object for the case-dossier engine (`caseboard case`).

A `CaseContext` is what a free-text clinical dictation becomes (see `intake.py`): a small,
queryable presentation contract every later stage reads from — the case-specific section
authors (WS-2), the literature lane (WS-3), the schematic figure authors (WS-4), and the PDF
surface (WS-5). It is deliberately decoupled from caseprep's clinical contracts, exactly like
`model.py`: this is an intake/presentation shape, not a clinical knowledge model.

Topic-agnostic by construction: the fields are generic case *dimensions* (geometry, history,
plan), never hardcoded clinical content. `to_topic()` is the seam that lets the existing
`build_manifest`/`classify_profile` pipeline run unchanged off a case, so WS-2+ can layer on
top without regressing `build`/`ask`/`cards`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical vocabularies for the two normalized enum-like fields. These are spatial/demographic
# tokens (text structure), NOT clinical content — the same carve-out `ontology.py` documents.
_LATERALITY = {
    "left": "left", "l": "left",
    "right": "right", "r": "right",
    "bilateral": "bilateral", "bilat": "bilateral",
    "midline": "midline", "central": "midline",
}
_SEX = {
    "m": "M", "male": "M", "man": "M", "boy": "M", "gentleman": "M",
    "f": "F", "female": "F", "woman": "F", "girl": "F", "lady": "F",
}


def _as_list(v) -> list[str]:
    """Coerce a scalar/None/list into a clean list[str] (LLM JSON is inconsistent here)."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()]


def _norm_laterality(v) -> str:
    return _LATERALITY.get(str(v or "").strip().lower(), "")


def _norm_sex(v) -> str:
    return _SEX.get(str(v or "").strip().lower(), "")


@dataclass
class CaseContext:
    # --- demographics ---
    age: int | None = None
    sex: str = ""                 # "M" | "F" | ""
    # --- presentation / imaging / history (prose; model- or user-supplied) ---
    presentation: str = ""        # chief complaint + HPI, normalized
    imaging: str = ""             # relevant imaging findings
    comorbidities: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)   # esp. anticoagulants/antiplatelets
    prior_surgery: str = ""
    functional_status: str = ""
    # --- case geometry: the levers that make a dossier case-specific ---
    laterality: str = ""          # "left" | "right" | "bilateral" | "midline" | ""
    level: str = ""               # spine-level token, e.g. "C5-6"
    location: str = ""            # anatomic location (cranial), e.g. "left frontal"
    # --- plan ---
    pathology: str = ""           # working diagnosis / lesion
    procedure: str = ""           # planned operation
    surgical_goal: str = ""       # e.g. resection, decompression, clip ligation
    constraints: list[str] = field(default_factory=list)   # hard constraints
    # --- provenance ---
    raw_dictation: str = ""
    source: str = ""              # "llm" | "deterministic"

    # ------------------------------------------------------------------ helpers
    def target(self) -> str:
        """The anatomic target: the spine level if present, else the location."""
        return self.level or self.location

    def to_topic(self) -> str:
        """Synthesize a bare topic string for the existing topic-driven pipeline.

        Space-joins, de-duplicated and whitespace-collapsed, the case geometry + plan
        (laterality, level/location, pathology, procedure). Falls back to the presentation
        prose and finally the literal "case" so `classify_profile`/`build_manifest` always
        receive a non-empty string.
        """
        parts = [self.laterality, self.target(), self.pathology, self.procedure]
        seen: list[str] = []
        for p in parts:
            p = (p or "").strip()
            if p and p.lower() not in {s.lower() for s in seen}:
                seen.append(p)
        topic = re.sub(r"\s+", " ", " ".join(seen)).strip()
        if topic:
            return topic
        if self.presentation.strip():
            return re.sub(r"\s+", " ", self.presentation.strip())[:60]
        return "case"

    def missing_critical(self) -> list[str]:
        """The few fields a case truly cannot proceed without — capped at 3 by construction.

        Conservative on purpose (locked decision: intake must not interrogate for everything).
        Laterality is captured but never demanded: a midline lesion legitimately has none.
        """
        missing: list[str] = []
        if not (self.procedure.strip() or self.pathology.strip()):
            missing.append("procedure or working diagnosis")
        if not self.target().strip():
            missing.append("anatomic target (spine level or location)")
        if not self.surgical_goal.strip():
            missing.append("surgical goal")
        return missing

    @classmethod
    def from_dict(cls, d: dict) -> "CaseContext":
        """Tolerant coercion of a (possibly messy) LLM/JSON dict into a CaseContext.

        Unknown keys are ignored; scalars are coerced into the list fields; age is int-ified;
        laterality/sex are normalized to their canonical tokens.
        """
        d = d or {}
        age = d.get("age")
        try:
            age = int(str(age).strip()) if age not in (None, "") else None
        except (TypeError, ValueError):
            age = None
        return cls(
            age=age,
            sex=_norm_sex(d.get("sex")),
            presentation=str(d.get("presentation") or "").strip(),
            imaging=str(d.get("imaging") or "").strip(),
            comorbidities=_as_list(d.get("comorbidities")),
            medications=_as_list(d.get("medications")),
            prior_surgery=str(d.get("prior_surgery") or "").strip(),
            functional_status=str(d.get("functional_status") or "").strip(),
            laterality=_norm_laterality(d.get("laterality")),
            level=str(d.get("level") or "").strip(),
            location=str(d.get("location") or "").strip(),
            pathology=str(d.get("pathology") or "").strip(),
            procedure=str(d.get("procedure") or "").strip(),
            surgical_goal=str(d.get("surgical_goal") or "").strip(),
            constraints=_as_list(d.get("constraints")),
            raw_dictation=str(d.get("raw_dictation") or "").strip(),
            source=str(d.get("source") or "").strip(),
        )
