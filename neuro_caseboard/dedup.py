"""Cross-section near-duplicate collapse (#9).

Deterministic and topic-agnostic: a normalised token-set (Jaccard) similarity pass over
claims, comparing only across *different* sections. The first occurrence is kept; later
near-duplicates are removed and the losing section gains a one-line cross-reference. No
phrase blacklists — the redundancy is structural (the Explorer emits the same concept
into multiple sub-slots for every topic), so a generic similarity test is the right tool.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
DEFAULT_THRESHOLD = 0.72


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def _similar(a: str, b: str, threshold: float) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= threshold


def dedup_sections(sections, *, threshold: float = DEFAULT_THRESHOLD):
    """Collapse cross-section near-duplicate claims in place; returns the sections."""
    seen: list[tuple[str, str]] = []  # (section_heading, dedup_text)
    for sec in sections:
        kept = []
        for claim in sec.claims:
            # Quarantine (off-target) claims bypass dedup entirely: kept verbatim and NEVER added
            # to the seen set — so they neither get removed nor suppress a legitimate later claim.
            if getattr(claim, "status", None) == "quarantine":
                kept.append(claim)
                continue
            dup_of = None
            for heading, text in seen:
                if heading != sec.heading and _similar(claim.dedup_text, text, threshold):
                    dup_of = heading
                    break
            if dup_of:
                ref = f"Also relevant — see {dup_of}"
                if ref not in sec.cross_refs:
                    sec.cross_refs.append(ref)
            else:
                kept.append(claim)
                seen.append((sec.heading, claim.dedup_text))
        sec.claims = kept
    return sections
