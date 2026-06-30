"""Post-synthesis answer verification: claim segmentation and per-claim entailment."""

import re
from dataclasses import dataclass, field

from neuro_caseboard.entailment import (
    _content_tokens,
    get_default_verifier,
    should_cite,
    unsupported_entities,
)

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
    bleed_terms: list = field(default_factory=list)
    # Markers on this claim that resolve to NO source in the premise key-set (invented/dangling).
    dangling: list = field(default_factory=list)


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

    def bleed_terms(self) -> list:
        """Unique medical entities flagged as bled (asserted but absent from the cited premise),
        in claim order, across all verdicts (survives ``merge_verifications``)."""
        out = []
        for v in self.claims:
            for t in getattr(v, "bleed_terms", None) or []:
                if t not in out:
                    out.append(t)
        return out

    def dangling_markers(self) -> list:
        """Citation markers that resolve to NO source in the premise key-set (invented/dangling),
        unique, in claim order. Distinct from ``unsupported_markers`` (markers on claims the verifier
        could not *entail*): a dangling marker points at a source that does not exist — a hard A1
        data-integrity failure that must surface, never abstain-into-supported."""
        out = []
        for v in self.claims:
            for m in getattr(v, "dangling", None) or []:
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
        # A1: a marker whose key is absent from the premise map resolves to NO source at all
        # (an invented/dangling [n] or [L#] beyond the real sources). That is distinct from a
        # PRESENT key with thin/empty text (a figure-only source), which should_cite abstain-keeps.
        # Collapsing the missing key into an empty premise would silently abstain-keep the bogus
        # marker; instead, flag it.
        dangling = [m for m in span.markers if m not in premises]
        premise = " ".join(p for m in span.markers for p in [premises.get(m)] if p)
        claim_text = _strip_markers(span.text)
        supported = should_cite(premise, claim_text, verifier)
        # Precision guard: a salient medical entity asserted in the claim but absent from its cited
        # premise is a cross-source bleed (recall can't catch it — the other tokens satisfy overlap).
        # Mirror should_cite's conservative abstain: when the premise is too thin to judge (e.g. an
        # empty PubMed abstract), skip the bleed check rather than flag an unjudgeable [L#] claim.
        min_tok = getattr(verifier, "min_premise_tokens", 5)
        bleed = []
        if len(_content_tokens(premise)) >= min_tok:
            bleed = sorted(unsupported_entities(claim_text, premise))
        if bleed:
            supported = False
        if dangling:  # a citation that points at a source that does not exist is never "supported"
            supported = False
        if not supported:  # count once per claim (don't double-count a recall-fail that also bleeds)
            n_unsup += 1
        verdicts.append(ClaimVerdict(span.text, span.markers, supported, len(premise), bleed, dangling))
    return AnswerVerification(verdicts, n_cited, n_unsup)


def merge_verifications(*verifications) -> "AnswerVerification":
    """Combine several AnswerVerification results (e.g. the textbook [n] answer and the
    literature [L#] narrative) into one. ``None`` entries are skipped; counts and claim
    lists are concatenated so groundedness/unsupported_markers span both."""
    claims, nc, nu = [], 0, 0
    for v in verifications:
        if v is None:
            continue
        claims.extend(v.claims)
        nc += v.n_cited_claims
        nu += v.n_unsupported
    return AnswerVerification(claims, nc, nu)


def verification_to_dict(v) -> "dict | None":
    if v is None:
        return None
    d = {
        "n_cited_claims": v.n_cited_claims,
        "n_unsupported": v.n_unsupported,
        "groundedness": v.groundedness(),
        "unsupported_markers": v.unsupported_markers(),
    }
    bleed = v.bleed_terms()
    if bleed:  # only when present, so the dict shape is unchanged for bleed-free verifications
        d["bleed_terms"] = bleed
    dangling = v.dangling_markers()
    if dangling:  # additive (like bleed_terms): dict shape unchanged when there are none
        d["dangling_markers"] = dangling
    return d


def verification_notice(v) -> str:
    """Human-readable needs-verification notice for display surfaces; '' when nothing to flag."""
    if v is None:
        return ""
    lines = []
    dangling = v.dangling_markers()
    # Entailment failures only: a claim flagged *solely* for a dangling marker is reported on the
    # dedicated line below, so it is not mislabeled "not entailed by the cited source".
    entail_unsupported = []
    for c in v.claims:
        if c.markers and not c.supported and not getattr(c, "dangling", None):
            for m in c.markers:
                if m not in entail_unsupported:
                    entail_unsupported.append(m)
    if entail_unsupported:
        markers = ", ".join(f"[{m}]" for m in entail_unsupported)
        lines.append(f"⚠ {len(entail_unsupported)} cited claim(s) flagged needs-verification "
                     f"(not entailed by the cited source): {markers}")
    if dangling:
        markers = ", ".join(f"[{m}]" for m in dangling)
        lines.append(f"⚠ {len(dangling)} citation marker(s) reference a source not in the source "
                     f"list (invented/dangling): {markers}")
    n_bleed = sum(1 for c in v.claims if getattr(c, "bleed_terms", None))
    if n_bleed:
        terms = ", ".join(v.bleed_terms())
        lines.append(f"⚠ {n_bleed} claim(s) assert a term not found in the cited source: {terms}")
    return "\n".join(lines)
