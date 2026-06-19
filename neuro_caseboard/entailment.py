"""Claim↔citation entailment verification (inference-only).

A claim earns an inline [n] corpus citation only if its cited span ENTAILS the claim. The default
LexicalVerifier is stdlib-only and deterministic; NLIVerifier (Task 1) is an optional, lazily
imported off-the-shelf cross-encoder NLI backend for production. Conservative: when a premise span
is too thin to judge, `should_cite` abstains and KEEPS the citation; the gate may only ever REMOVE
a weak citation — never add or re-point one.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "and", "for", "with", "that", "this", "are", "must", "its", "into",
         "from", "their", "which", "may", "can", "not", "but", "all", "any", "per"}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if len(t) >= 3 and t not in _STOP}


@runtime_checkable
class ClaimVerifier(Protocol):
    def entails(self, premise: str, hypothesis: str) -> bool: ...


class LexicalVerifier:
    """Deterministic token-overlap entailment proxy (no model/deps). `entails` is True when the
    hypothesis's content tokens are sufficiently recalled by the premise."""

    def __init__(self, threshold: float = 0.18, min_premise_tokens: int = 5) -> None:
        self.threshold = threshold
        self.min_premise_tokens = min_premise_tokens

    def entails(self, premise: str, hypothesis: str) -> bool:
        p = _content_tokens(premise)
        h = _content_tokens(hypothesis)
        if not h:
            return True
        return (len(p & h) / len(h)) >= self.threshold


def should_cite(premise: str, hypothesis: str, verifier: ClaimVerifier) -> bool:
    """Keep the citation unless the verifier positively rejects a JUDGEABLE premise. Abstain→keep
    when the premise is too thin to judge (cannot disprove)."""
    min_tok = getattr(verifier, "min_premise_tokens", 5)
    if len(_content_tokens(premise)) < min_tok:
        return True
    return bool(verifier.entails(premise, hypothesis))
