"""Quoted-span verification (FIX_PLAN §3.3) — the verbatim-quote contract.

For each evidential claim, the synthesizer commits a verbatim supporting quote; we string-match
it back into the chunk it cites. A quote that matches has *precision 1.0 against a fabricated
citation, by construction* — deterministic, free, and needing no NLI model. The quote lives in
a structured sidecar and NEVER enters the prose (§3.3.1): the reader sees an ordinary paragraph;
the quote is what they get when they click the citation.

Only *evidential* claims (a number, threshold, comparator, recommendation, trial result) carry a
quote. *Connective* teaching prose is held to the entity-bleed check instead (answer_verify), so
the answer stays explanatory rather than a chain of stitched quotations.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    """Lowercase + collapse whitespace: verbatim up to spacing/case, which is all a PDF text
    layer preserves reliably (line wraps become spaces)."""
    return _WS.sub(" ", (s or "").lower()).strip()


def quote_matches(quote: str, chunk: str, *, threshold: float = 0.90) -> tuple[bool, float]:
    """Is ``quote`` really present in ``chunk``? Normalized-substring first (exact verbatim),
    then a longest-common-substring ratio for minor OCR/hyphenation drift. Returns
    ``(matched, score)`` where score is 1.0 for a clean substring hit."""
    q, c = _norm(quote), _norm(chunk)
    if not q:
        return False, 0.0
    if q in c:
        return True, 1.0
    match = SequenceMatcher(None, q, c).find_longest_match(0, len(q), 0, len(c))
    score = match.size / len(q)
    return score >= threshold, score


@dataclass
class EvidenceSpan:
    claim: str
    marker: str        # "1", "L3", "D2" — the [n]/[L#]/[D#] the claim cited
    quote: str         # the model's verbatim supporting sentence (sidecar only, never rendered)
    matched: bool
    score: float


def verify_spans(items, premises: dict, *, threshold: float = 0.90) -> list[EvidenceSpan]:
    """Verify model-supplied quotes against the cited premises. ``items`` is an iterable of
    ``{claim, marker, quote}`` dicts; ``premises`` maps marker -> cited chunk text. A quote whose
    marker has no premise, or that does not match, is ``matched=False`` (a rejected citation)."""
    out = []
    for it in items:
        marker = str(it.get("marker", "")).lstrip("[").rstrip("]")
        quote = it.get("quote", "") or ""
        premise = premises.get(marker, "")
        matched, score = quote_matches(quote, premise, threshold=threshold) if premise else (False, 0.0)
        out.append(EvidenceSpan(claim=it.get("claim", ""), marker=marker,
                                quote=quote, matched=matched, score=score))
    return out


_EXTRACT_SYSTEM = (
    "You extract supporting evidence, not prose. For each EVIDENTIAL claim in the answer (a claim "
    "carrying a number, threshold, comparator, recommendation, or trial result and a bracketed "
    "citation like [2] or [L3]), output the VERBATIM sentence from that numbered source that "
    "supports it. Copy the sentence exactly as written in the source — do not paraphrase, do not "
    "fix typos. Output ONLY a JSON array of objects {\"claim\": str, \"marker\": str, \"quote\": "
    "str}, marker being the citation number without brackets (e.g. \"2\", \"L3\"). No prose."
)


def extract_and_verify(answer: str, premises: dict, synth_client, *,
                       threshold: float = 0.90) -> list[EvidenceSpan]:
    """One LLM pass to extract each evidential claim's verbatim supporting quote, then verify each
    quote against its cited premise. Returns the evidence sidecar. On any parse/LLM failure returns
    ``[]`` (no sidecar) rather than blocking the answer — verification is additive."""
    sources = "\n\n".join(f"[{m}] {t}" for m, t in premises.items())
    user = f"Answer:\n{answer}\n\nNumbered sources:\n{sources}"
    try:
        raw = synth_client.generate(_EXTRACT_SYSTEM, user, [], route="citation_extract")
        items = json.loads(_strip_code_fence(raw))
        if not isinstance(items, list):
            return []
    except Exception:
        return []
    return verify_spans(items, premises, threshold=threshold)


def _strip_code_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-z]*\n?|\n?```$", "", s).strip()
    return s


def span_match_rate(spans) -> float | None:
    """Fraction of evidential quotes that string-matched their cited chunk — the D15 metric.
    ``None`` when there are no spans (undefined, not a perfect 1.0 — mirrors groundedness)."""
    spans = list(spans)
    if not spans:
        return None
    return sum(1 for s in spans if s.matched) / len(spans)
