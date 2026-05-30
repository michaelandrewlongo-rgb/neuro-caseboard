"""Salient-tag vocabulary + whole-word, first-occurrence matcher for figure marks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Generic words that must never mark a briefing word (precision guardrail).
STOP_TAGS: frozenset[str] = frozenset({
    "patient", "image", "imaging", "figure", "scan", "view", "mri", "ct", "cta",
    "ctp", "dsa", "angiogram", "angiography", "brain", "head", "left", "right",
    "axial", "coronal", "sagittal", "case", "study", "diagram", "illustration",
    "normal", "abnormal", "anatomy", "vessel", "artery", "vein",
})

MIN_TAG_LEN = 4


@dataclass
class Mark:
    term: str
    start: int
    end: int
    candidate_keys: list[str] = field(default_factory=list)


def _is_salient(tag: str) -> bool:
    if " " in tag:            # multi-word phrases are specific
        return True
    return len(tag) >= MIN_TAG_LEN and tag not in STOP_TAGS


def build_vocabulary(records) -> dict[str, list[str]]:
    """tag -> sorted list of figure keys carrying it (salient tags only)."""
    vocab: dict[str, list[str]] = {}
    for rec in records:
        key = f"{rec.source}:{rec.fig_id}"
        for tag in rec.tags:
            t = tag.strip().lower()
            if not _is_salient(t):
                continue
            vocab.setdefault(t, [])
            if key not in vocab[t]:
                vocab[t].append(key)
    return {t: sorted(keys) for t, keys in vocab.items()}


def find_marks(text: str, vocabulary: dict[str, list[str]]) -> list[Mark]:
    """First whole-word occurrence (in document order) of each salient term.
    Longer terms win when spans would overlap."""
    found: list[Mark] = []
    for term in sorted(vocabulary, key=len, reverse=True):
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        m = pattern.search(text)
        if m:
            found.append(Mark(term=term, start=m.start(), end=m.end(),
                              candidate_keys=list(vocabulary[term])))
    found.sort(key=lambda mk: mk.start)
    kept: list[Mark] = []
    last_end = -1
    for mk in found:
        if mk.start >= last_end:
            kept.append(mk)
            last_end = mk.end
    return kept
