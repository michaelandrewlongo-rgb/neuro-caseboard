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


# ---------------------------------------------------------------------------
# Task 2 — LLM-backed query_analyze() with fail-open JSON parse
# ---------------------------------------------------------------------------

CLARIFY_THRESHOLD = 0.6

ANALYZE_SYSTEM_PROMPT = (
    "You disambiguate a neurosurgical question that may conflate two named VARIANTS "
    "of one procedure. Given the question and retrieved passages, return ONLY a JSON "
    "object, no prose, with keys:\n"
    '  "ambiguous": true|false — true ONLY if the passages describe >=2 distinct named variants;\n'
    '  "axis": a short label for the variant axis, or null;\n'
    '  "variants": a list of {"label": variant name, "rewrite": the question rewritten to scope ONLY that variant};\n'
    '  "chosen": the label of the variant most consistent with the question + passages, or null;\n'
    '  "confidence": 0.0-1.0 — how clearly one variant dominates (low if the passages are split evenly).\n'
)


@dataclass
class VariantRewrite:
    label: str
    rewrite: str


@dataclass
class QueryAnalysis:
    ambiguous: bool
    axis: str | None = None
    variants: list[VariantRewrite] = field(default_factory=list)
    chosen: VariantRewrite | None = None
    confidence: float = 0.0


def _parse_analysis(text):
    """Parse the model reply into a QueryAnalysis, or raise an exception
    (caught by query_analyze's fail-open guard)."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in analyze reply")
    obj = json.loads(cleaned[start:end + 1])
    if not obj.get("ambiguous"):
        return QueryAnalysis(ambiguous=False)
    raw_variants = obj.get("variants")
    variants = [VariantRewrite(label=str(v.get("label", "")).strip(),
                               rewrite=str(v.get("rewrite", "")).strip())
                for v in (raw_variants if isinstance(raw_variants, list) else [])
                if isinstance(v, dict) and v.get("label") and v.get("rewrite")]
    chosen = next((v for v in variants if v.label == obj.get("chosen")), None)
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    if len(variants) < 2 or chosen is None:
        return QueryAnalysis(ambiguous=False)
    return QueryAnalysis(ambiguous=True, axis=obj.get("axis"),
                         variants=variants, chosen=chosen, confidence=conf)


def query_analyze(question, hits, synth_client):
    """One LLM pass: detect the variant axis, rewrite per variant, pick + score.
    NEVER raises: any failure -> QueryAnalysis(ambiguous=False)."""
    try:
        passages = "\n\n".join(getattr(h, "text", "") for h in hits)
        user = f"Question: {question}\n\nPassages:\n{passages}"
        reply = synth_client.generate(ANALYZE_SYSTEM_PROMPT, user, [])
        return _parse_analysis(reply)
    except Exception:
        return QueryAnalysis(ambiguous=False)
