"""Post-synthesis answer verification: claim segmentation and per-claim entailment."""

import re
from dataclasses import dataclass, field

from neuro_caseboard.entailment import get_default_verifier, should_cite

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


@dataclass
class ClaimVerdict:
    text: str
    markers: list
    supported: bool
    premise_chars: int


@dataclass
class AnswerVerification:
    claims: list
    n_cited_claims: int
    n_unsupported: int

    def groundedness(self) -> float:
        if self.n_cited_claims == 0:
            return 1.0
        return 1.0 - self.n_unsupported / self.n_cited_claims

    def unsupported_markers(self) -> list:
        out = []
        for v in self.claims:
            if v.markers and not v.supported:
                for m in v.markers:
                    if m not in out:
                        out.append(m)
        return out


def _strip_markers(text: str) -> str:
    return _MARKER.sub("", text).strip()


def verify_answer(answer: str, premises: dict, *, verifier=None) -> "AnswerVerification":
    verifier = verifier or get_default_verifier()
    verdicts, n_cited, n_unsup = [], 0, 0
    for span in segment_claims(answer):
        if not span.markers:
            verdicts.append(ClaimVerdict(span.text, span.markers, True, 0))
            continue
        n_cited += 1
        premise = " ".join(p for m in span.markers for p in [premises.get(m)] if p)
        supported = should_cite(premise, _strip_markers(span.text), verifier)
        if not supported:
            n_unsup += 1
        verdicts.append(ClaimVerdict(span.text, span.markers, supported, len(premise)))
    return AnswerVerification(verdicts, n_cited, n_unsup)


def verification_to_dict(v) -> "dict | None":
    if v is None:
        return None
    return {
        "n_cited_claims": v.n_cited_claims,
        "n_unsupported": v.n_unsupported,
        "groundedness": v.groundedness(),
        "unsupported_markers": v.unsupported_markers(),
    }


def verification_notice(v) -> str:
    """Human-readable needs-verification notice for display surfaces; '' when nothing to flag."""
    if v is None or v.n_unsupported <= 0:
        return ""
    markers = ", ".join(f"[{m}]" for m in v.unsupported_markers())
    return (f"⚠ {v.n_unsupported} cited claim(s) flagged needs-verification "
            f"(not entailed by the cited source): {markers}")
