"""Post-synthesis answer verification: claim segmentation (and, later, per-claim entailment)."""

import re
from dataclasses import dataclass, field

_MARKER = re.compile(r"\[(L?\d+)\]")
_SENT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ClaimSpan:
    text: str
    markers: list = field(default_factory=list)


def segment_claims(answer: str) -> list:
    answer = (answer or "").strip()
    if not answer:
        return []
    spans = []
    for sent in _SENT.split(answer):
        sent = sent.strip()
        if sent:
            spans.append(ClaimSpan(text=sent, markers=_MARKER.findall(sent)))
    return spans
