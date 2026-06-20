"""Quantitative decision-support extraction for Ask answers (BACKLOG P2 #6).

Pure regex/parse over the grounded answer text — never fabricates a number; only surfaces spans
literally present. Mirrors app/ask_confidence.py (the app passes result.answer; tests pass strings)."""
from __future__ import annotations

import re
from dataclasses import dataclass

METRIC_PATTERNS = [
    ("count", re.compile(r"\bn\s?=\s?\d+\b", re.I)),
    ("interval", re.compile(r"\b(?:95\s?%\s?CI|\d{1,3}(?:\.\d+)?\s?%?\s?CI)\b", re.I)),
    ("pvalue", re.compile(r"\bp\s?[<>=]\s?0?\.\d+\b", re.I)),
    ("percent", re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")),
    ("duration", re.compile(r"\b\d+(?:\.\d+)?\s?(?:day|week|month|year)s?\b", re.I)),
    ("ratio", re.compile(r"\b\d+(?:\.\d+)?\s?(?:to|–|/)\s?\d+(?:\.\d+)?\b", re.I)),
]
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_COMPARATIVE = re.compile(
    r"\b(?:better|worse|higher|lower|superior|inferior|more|less|greater|fewer|"
    r"reduc\w*|increas\w*|improv\w*|outperform\w*|favou?rs?)\b", re.I)


@dataclass
class Metric:
    clause: str
    value: str
    kind: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.strip()) if s.strip()]


def extract_metrics(text: str) -> list[Metric]:
    out: list[Metric] = []
    seen: set[tuple[str, str]] = set()
    for sent in _sentences(text):
        for kind, pat in METRIC_PATTERNS:
            for m in pat.finditer(sent):
                val = m.group(0).strip()
                key = (sent, val)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Metric(clause=sent, value=val, kind=kind))
    return out


def has_quantitative_support(text: str) -> bool:
    return bool(extract_metrics(text))


def unquantified_comparisons(text: str) -> list[str]:
    flagged = []
    for sent in _sentences(text):
        if _COMPARATIVE.search(sent) and not any(p.search(sent) for _, p in METRIC_PATTERNS):
            flagged.append(sent)
    return flagged


def summarize(metrics) -> dict:
    counts: dict = {}
    for m in metrics:
        counts[m.kind] = counts.get(m.kind, 0) + 1
    return counts
