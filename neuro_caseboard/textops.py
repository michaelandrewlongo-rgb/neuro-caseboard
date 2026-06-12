"""Topic-agnostic text helpers.

These key off punctuation and structure only — never clinical content — so they
generalise across every neurosurgical subspecialty.
"""

from __future__ import annotations

import re

_ENUM = re.compile(r"\(\d+\)")
_SCRUB_TOKENS = ("VERIFY:", "[needs_patient_fact]", "[needs_evidence]")


def scrub_question(text: str) -> str:
    """Strip Explorer formatting tokens and normalise whitespace."""
    out = text or ""
    for tok in _SCRUB_TOKENS:
        out = out.replace(tok, "")
    return " ".join(out.split())


def split_compound(text: str) -> list[str]:
    """Split an over-dense bullet into atomic sub-items (#6).

    Returns ``[]`` when the bullet is a single, atomic statement. A bullet is
    "compound" when it stacks multiple questions, enumerated steps, or a
    semicolon list — purely structural signals.
    """
    t = (text or "").strip()
    if not t:
        return []

    # multiple questions
    if t.count("?") >= 2:
        parts = [p.strip() for p in t.split("?")]
        return [p + "?" for p in parts if p]

    # enumerated steps: (1) ... (2) ...
    if len(_ENUM.findall(t)) >= 2:
        pieces = [p.strip(" ;,.") for p in _ENUM.split(t)]
        return [p for p in pieces if p]

    # semicolon list of >= 2 separators (3+ clauses)
    if t.count(";") >= 2:
        return [p.strip() for p in t.split(";") if p.strip()]

    return []
