"""Fine-grained Build evidence grading (BACKLOG P2 #5).

Pure classifier: maps grading signals already available in compile.py to an informative category,
replacing the overly-broad "verify" bucket. ``summary_bucket`` collapses each category back to the
existing 3-way EvidenceSummary so counts/invariants do not regress."""
from __future__ import annotations

from dataclasses import dataclass

GRADE_LABEL = {
    "directly-supported": "Directly supported",
    "multi-source": "Supported by multiple sources",
    "standard-practice": "Standard practice (weakly cited)",
    "attending-preference": "Attending preference",
    "conflicting": "Conflicting evidence",
    "unsupported": "Unsupported or quarantined",
}
GRADES = tuple(GRADE_LABEL)


@dataclass(frozen=True)
class GradeSignals:
    audit_status: str            # supported | needs_review | no_evidence | off_target
    n_sources: int = 0           # # accepted supporting papers
    cited: bool = False          # at least one [n] citation resolved
    has_conflict: bool = False   # contradicting evidence present
    is_preference: bool = False  # attending/operative preference provenance


def grade(sig: GradeSignals) -> str:
    if sig.audit_status == "off_target":
        return "unsupported"
    if sig.has_conflict:
        return "conflicting"
    if sig.is_preference:
        return "attending-preference"
    if sig.audit_status == "supported":
        return "multi-source" if sig.n_sources >= 2 else "directly-supported"
    if sig.audit_status == "needs_review":
        return "standard-practice"
    return "unsupported"


def summary_bucket(category: str) -> str:
    if category in ("directly-supported", "multi-source"):
        return "supported"
    return "to_verify"
