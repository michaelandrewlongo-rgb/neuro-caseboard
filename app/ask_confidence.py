"""Per-claim confidence for Ask answers (BACKLOG P2 #4).

Pure parsing/classification over the synthesized answer's inline ``[n]`` citation markers, so the
logic is unit-testable without Streamlit/engine/network. The Ask lane renders the result; the app
builds ``source_lane`` from result.citations (textbook) vs result.literature.citations (literature)."""
from __future__ import annotations

import re
from dataclasses import dataclass

STATUS_LABEL = {
    "consensus": "multi-source consensus",
    "single-source": "single source",
    "conflict": "source conflict",
    "literature-only": "literature only",
    "unsupported": "not found in corpus",
}
STATUS_MARK = {
    "consensus": "✓✓",
    "single-source": "✓",
    "conflict": "⚠",
    "literature-only": "≈",
    "unsupported": "∅",
}

_MARKER = re.compile(r"\[(\d+)\]")
# split after sentence-ending punctuation that may be followed by citation markers
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass
class ClaimConfidence:
    text: str
    status: str
    sources: tuple[int, ...]


def cited_sources(claim: str) -> tuple[int, ...]:
    seen: list[int] = []
    for m in _MARKER.finditer(claim):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return tuple(seen)


def split_claims(answer: str) -> list[str]:
    return [c for c in (s.strip() for s in _SENT.split(answer.strip())) if c]


def classify(sources, source_lane, conflicting) -> str:
    if not sources:
        return "unsupported"
    if any(s in conflicting for s in sources):
        return "conflict"
    lanes = [source_lane.get(s, "textbook") for s in sources]
    if all(ln == "literature" for ln in lanes):
        return "literature-only"
    n_textbook = sum(1 for ln in lanes if ln == "textbook")
    return "consensus" if n_textbook >= 2 else "single-source"


def grade_answer(answer: str, source_lane, *, conflicting=frozenset()) -> list[ClaimConfidence]:
    out = []
    for claim in split_claims(answer):
        srcs = cited_sources(claim)
        out.append(ClaimConfidence(text=claim, status=classify(srcs, source_lane, conflicting),
                                   sources=srcs))
    return out


def summarize(claims) -> dict:
    counts: dict = {}
    for c in claims:
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts
