# neuro_core/query_analyze.py
"""Query-adaptive variant disambiguation.

A cheap gate decides whether a query may conflate two named VARIANTS of one
procedure (e.g. unilateral FTP vs. bifrontal decompressive craniectomy). When it
trips, query_analyze() spends one LLM pass to pick the variant + confidence.

Like live_reconcile.py, query_analyze() NEVER raises into the answer path: any
failure -> QueryAnalysis(ambiguous=False), so the normal answer always stands.
"""
import json
import re
from dataclasses import dataclass, field

# Curated neuro procedure-variant taxonomy.
#   triggers: terms in the QUESTION that name the (ambiguous) parent procedure.
#   variants: label -> key terms whose presence in retrieved passages names that variant.
VARIANT_AXES = {
    "decompressive-craniectomy": {
        "triggers": ["decompressive craniectomy", "decompressive hemicraniectomy",
                     "decompressive craniotomy", "dhc"],
        "variants": {
            "unilateral FTP hemicraniectomy":
                ["frontotemporoparietal", "hemicraniectomy"],
            "bifrontal (Kjellberg) decompression":
                ["bifrontal", "bicoronal", "kjellberg"],
        },
    },
    "anterior-cervical": {
        "triggers": ["anterior cervical", "acdf"],
        "variants": {
            "ACDF (discectomy and fusion)": ["discectomy", "acdf"],
            "anterior cervical corpectomy": ["corpectomy"],
        },
    },
    "pterional-approach": {
        "triggers": ["pterional", "frontotemporal approach"],
        "variants": {
            "standard pterional craniotomy": ["pterional"],
            "orbitozygomatic approach": ["orbitozygomatic"],
        },
    },
    "csf-diversion": {
        "triggers": ["csf diversion", "drain placement"],
        "variants": {
            "external ventricular drain (EVD)": ["ventriculostomy", "ventricular drain", "evd"],
            "lumbar drain": ["lumbar drain"],
        },
    },
}


@dataclass
class Gate:
    tripped: bool
    axis: str | None = None


def _norm(s):
    return (s or "").lower()


def ambiguity_gate(question, hits):
    """Cheap, no-LLM. Trips when the question names an ambiguous parent procedure
    (taxonomy trigger) OR the retrieved passages name >=2 variants of one axis."""
    q = _norm(question)
    blob = " ".join(_norm(getattr(h, "text", "")) for h in hits)
    for axis, spec in VARIANT_AXES.items():
        trigger = any(t in q for t in spec["triggers"])
        named = sum(1 for terms in spec["variants"].values()
                    if any(term in blob for term in terms))
        if trigger or named >= 2:
            return Gate(tripped=True, axis=axis)
    return Gate(tripped=False)
