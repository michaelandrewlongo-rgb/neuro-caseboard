"""Clinical Claim Review gate (FIX_PLAN §5 / Decision Card SP1).

A deterministic, model-free layer between synthesis and display. It reuses the machinery already
built on this branch — the §3.3 evidence spans (verbatim-quote / precision-1.0 match) and
answer_verify's sentence+marker segmentation — and adds category tagging + currency-staleness
tiering, then assembles a DecisionCard.

Locked design decisions (domain-blind advisory, 2026-07-11):
- Staleness fires ONLY on a sentence that itself asserts currency. Threshold STALENESS_YEARS=5
  (soft cues), strong-cue tier = ceil(0.6*5)=3 (anchor: guideline half-life ~5.8y). A strong-cue
  claim ("newly/latest") citing NO dated ([L#]/[D#]) marker also flags.
- Fail action = SOFTEN in place, never hide. A failing claim becomes status="uncertain" and is
  carried in `uncertainties`; nothing is deleted from prose (`prose` is the verbatim answer). The
  soften-vs-collapse render choice is an SP2 knob — this data layer always carries every claim.

Failure-safe: any internal error returns a prose-only DecisionCard, never raises into the pipeline.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from neuro_caseboard.answer_verify import _strip_markers, segment_claims

STALENESS_YEARS_DEFAULT = 5


# --- category tagging (first match wins; ordered by specificity) ------------------------------
# ponytail: keyword/regex tagger — cheap and model-free. Upgrade path is a one-shot LLM tag if the
# SP3 labeled fixture shows misses; until then this targets the gate + groups the card, no more.
_CATEGORY_RULES = [
    ("contraindication", re.compile(r"contraindicat|\bshould not\b|\bmust not\b|\bnot recommended\b", re.I)),
    ("regulatory", re.compile(r"\bFDA\b|\bapproved\b|\bcleared\b|\boff-?label\b", re.I)),
    ("comparative", re.compile(
        r"\bsuperior\b|\binferior\b|\bbetter than\b|\bworse than\b|\bversus\b|\bvs\.?\b|"
        r"compared (?:to|with)|non-?inferior|\bmore effective\b|\bless effective\b", re.I)),
    ("threshold", re.compile(
        r"\bthreshold\b|\bcut-?off\b|"
        r"\d+(?:\.\d+)?\s?(?:mm|cm|mg|ml|%|mmhg|mm hg|hours?|hrs?|days?|weeks?|units?)\b|"
        r"[<>≤≥]\s?\d", re.I)),
    ("indication", re.compile(
        r"\bindicat(?:ed|ion)\b|\bfirst-?line\b|\brecommended\b|\btreatment of choice\b|"
        r"\bis used (?:to|for)\b", re.I)),
]


def category(claim: str) -> str:
    """Management category of a claim, or "other" (connective/teaching prose). Used to route the
    claim into the card and to decide whether the freshness/span gate applies to it."""
    for name, rx in _CATEGORY_RULES:
        if rx.search(claim or ""):
            return name
    return "other"


# --- currency-cue tiering ---------------------------------------------------------------------
_STRONG_CUE = re.compile(
    r"\b(?:newly|latest|newest|just approved|just released|most recent|breakthrough|"
    r"cutting-edge)\b", re.I)
_SOFT_CUE = re.compile(
    r"\bnow (?:the )?standard\b|\bcurrent(?:ly)?\b|\bpresent-day\b|\bcontemporary\b|\bmodern\b|"
    r"\bnowadays\b|\bat present\b|\bto date\b|\bstate[- ]of[- ]the[- ]art\b", re.I)


def currency_cue(claim: str) -> "str | None":
    """"strong" | "soft" | None — how loudly the sentence asserts recency. Only a cued sentence is
    eligible for the staleness flag, which keeps the flag rare (the false-positive discipline)."""
    if _STRONG_CUE.search(claim or ""):
        return "strong"
    if _SOFT_CUE.search(claim or ""):
        return "soft"
    return None


def _tier_years(cue: str, base: int) -> int:
    return math.ceil(base * 0.6) if cue == "strong" else base


def is_stale(cue, year, now_year, *, base: int = STALENESS_YEARS_DEFAULT) -> bool:
    """A currency-cued claim is stale when its freshest dated source is older than the cue's tier
    (soft=base years, strong=ceil(0.6*base)). A strong-cue claim with NO dated source (year None)
    is stale by construction — a "latest/newly approved" claim resting only on a textbook."""
    if not cue:
        return False
    if year is None:
        return cue == "strong"
    return (now_year - int(year)) > _tier_years(cue, base)


# --- the reviewed data structures -------------------------------------------------------------
@dataclass
class ReviewedClaim:
    text: str                       # the claim sentence, citation markers stripped (display copy)
    markers: list = field(default_factory=list)
    category: str = "other"
    quote: str = ""                 # verbatim supporting sentence (sidecar; from the EvidenceSpan)
    span_matched: bool = False
    status: str = "settled"         # "settled" | "uncertain"
    flags: list = field(default_factory=list)   # stale_currency | unmatched_span
    year: "int | None" = None


@dataclass
class DecisionCard:
    prose: str                      # the answer, VERBATIM — the card is a lens, never a rewrite
    bottom_line: list = field(default_factory=list)        # settled recommendation-type claims
    decision_furniture: list = field(default_factory=list)  # settled threshold/comparator claims
    uncertainties: list = field(default_factory=list)      # the amber lane (status=="uncertain")
    coverage_gaps: list = field(default_factory=list)      # question limbs the answer did not address
    conflicts: list = field(default_factory=list)          # sentences stating a source disagreement


_BOTTOM_LINE_CATS = {"indication", "contraindication", "regulatory", "trial"}
_FURNITURE_CATS = {"threshold", "comparative"}
_CONFLICT = re.compile(r"\bdisagree|\bcontradict|\bconflicting\b|\bin contrast\b|\bwhereas\b|"
                       r"\bhowever,", re.I)

# Question words stripped before picking a limb's key term, so "Compare X and Y" keys on X / Y.
_Q_STOP = frozenset({
    "compare", "comparison", "what", "which", "how", "is", "are", "the", "for", "of", "a", "an",
    "and", "or", "vs", "versus", "do", "does", "between", "with", "in", "on", "to", "difference",
    "when", "why", "who", "that", "this", "should", "can", "role"})
_LIMB_SPLIT = re.compile(r"\s+(?:and|vs\.?|versus|or)\s+|,", re.I)


def _coverage_gaps(question: str, answer: str) -> list:
    """Deterministic limb-coverage: split the question on and/vs/or/commas, take each limb's
    longest non-question token, and flag limbs whose key term never appears in the answer.
    ponytail: regex limb-splitting is display-only (never withholds a claim) and has a known
    ceiling (misses implicit limbs, over-splits lists); upgrade to an LLM limb extractor only if
    the SP3 fixture shows it matters."""
    q = (question or "").strip()
    if not q:
        return []
    ans = (answer or "").lower()
    gaps = []
    for limb in _LIMB_SPLIT.split(q):
        toks = [t for t in re.findall(r"[a-z0-9-]+", limb.lower())
                if t not in _Q_STOP and len(t) > 2]
        if not toks:
            continue
        key = max(toks, key=len)
        if key not in ans:
            gaps.append(f"did not address: {key}")
    return gaps


def build_decision_card(answer, *, spans, marker_year, now_year, question: str = "",
                        staleness_years: int = STALENESS_YEARS_DEFAULT) -> DecisionCard:
    """Assemble a DecisionCard from the answer + its evidence spans. `spans` is a list of
    EvidenceSpan (claim, marker, quote, matched); `marker_year` maps a marker ("1"/"L3"/"D2") to
    the source's publication year (or None for undated/textbook). Deterministic and failure-safe."""
    try:
        return _build(answer or "", spans, marker_year or {}, now_year, question, staleness_years)
    except Exception:   # never let the review layer blank an answer
        return DecisionCard(prose=answer or "")


def _build(answer, spans, marker_year, now_year, question, staleness_years) -> DecisionCard:
    reviewed = []
    for s in spans or []:
        claim = getattr(s, "claim", "") or ""
        marker = str(getattr(s, "marker", "")).lstrip("[").rstrip("]")
        matched = bool(getattr(s, "matched", False))
        cue = currency_cue(claim)
        year = marker_year.get(marker)
        flags = []
        if not matched:
            flags.append("unmatched_span")
        if is_stale(cue, year, now_year, base=staleness_years):
            flags.append("stale_currency")
        reviewed.append(ReviewedClaim(
            text=_strip_markers(claim), markers=[marker] if marker else [],
            category=category(claim), quote=getattr(s, "quote", "") or "",
            span_matched=matched, status="uncertain" if flags else "settled",
            flags=flags, year=year))

    settled = [r for r in reviewed if r.status == "settled"]
    return DecisionCard(
        prose=answer,
        bottom_line=[r for r in settled if r.category in _BOTTOM_LINE_CATS],
        decision_furniture=[r for r in settled if r.category in _FURNITURE_CATS],
        uncertainties=[r for r in reviewed if r.status == "uncertain"],
        coverage_gaps=_coverage_gaps(question, answer),
        conflicts=[c.text for c in segment_claims(answer) if _CONFLICT.search(c.text)],
    )
