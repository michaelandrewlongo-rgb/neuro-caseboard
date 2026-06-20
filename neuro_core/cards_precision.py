"""Cards retrieval precision (BACKLOG P4 #12).

Pure post-filter over already-retrieved CardHits — no embedder/index/network — so the precision
logic is unit-testable. Two robust, scale-independent improvements plus an opt-in relevance floor:

  1. Anatomical-level precision: if the query names spinal levels (e.g. "C5-6"), drop cards that
     name a DIFFERENT level (the "adjacent / anatomically mismatched" defect). Cards with no level
     or that cover the queried level are kept.
  2. Exact-term boost: reorder by base score + exact query-term overlap (a tie-breaker that favours
     literal matches; small weight so it never overrides a confident reranker).
  3. Optional relevance threshold (``keep_ratio`` > 0): suppress hits weak relative to the top hit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_STOP = {"the", "and", "for", "with", "what", "which", "of", "to", "in", "on", "at", "is", "a", "an"}
_WORD = re.compile(r"[a-z0-9]+")
# Spinal levels: "C5-6", "C5-C6", "L4-5", "T12-L1", or a bare "C5".
_LEVEL_RANGE = re.compile(r"\b([clts])(\d{1,2})\s*[-–]\s*([clts]?)(\d{1,2})\b", re.I)
_LEVEL_SINGLE = re.compile(r"\b([clts])(\d{1,2})\b", re.I)


@dataclass
class RefinedCards:
    cards: list = field(default_factory=list)
    note: str = ""


def query_terms(q: str) -> set:
    return {w for w in _WORD.findall((q or "").lower()) if len(w) > 2 and w not in _STOP}


def spinal_levels(text: str) -> set:
    t = (text or "").lower()
    out: set = set()
    for m in _LEVEL_RANGE.finditer(t):
        a_l, a_n, b_l, b_n = m.groups()
        out.add(f"{a_l}{a_n}")
        out.add(f"{b_l or a_l}{b_n}")
    for m in _LEVEL_SINGLE.finditer(t):
        out.add(f"{m.group(1)}{m.group(2)}")
    return out


def _hit_text(hit) -> str:
    return " ".join(str(getattr(hit, a, "") or "") for a in ("question_text", "answer_text", "text"))


def level_ok(q_levels: set, hit) -> bool:
    """Keep the card unless the query names level(s) the card contradicts. A card with no level, or
    one that covers the queried level(s), is kept; one naming only different levels is dropped."""
    if not q_levels:
        return True
    hl = spinal_levels(_hit_text(hit))
    return (not hl) or q_levels <= hl


def exact_overlap(q_terms: set, hit) -> int:
    return len(q_terms & {w for w in _WORD.findall(_hit_text(hit).lower())})


def refine(hits, question, *, k, exact_weight: float = 0.05, keep_ratio: float = 0.0) -> RefinedCards:
    q_levels = spinal_levels(question)
    q_terms = query_terms(question)

    kept = [h for h in hits if level_ok(q_levels, h)]

    def adj(h) -> float:
        return (getattr(h, "score", 0.0) or 0.0) + exact_weight * exact_overlap(q_terms, h)

    kept = sorted(kept, key=adj, reverse=True)

    if keep_ratio > 0 and kept:
        top = adj(kept[0])
        if top > 0:
            kept = [h for h in kept if adj(h) >= keep_ratio * top]

    kept = kept[:k]
    note = "" if kept else "No cards matched this query precisely enough."
    return RefinedCards(cards=kept, note=note)
