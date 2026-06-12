"""Figure caption completion and relevance (#7).

textbook-rag's ``extract_caption`` returns only the *first physical line* matching a
figure label, so multi-line captions arrive truncated ("...construct from a"). Given
the figure page's text we reassemble the full caption; without it we keep the first
line. The relevance line is subspecialty-neutral — it links the figure to the claim it
supports and its citation, and fabricates no clinical content.
"""

from __future__ import annotations

import re

_FIG_LABEL = re.compile(r"^\s*(fig(?:ure)?|plate)\b", re.IGNORECASE)


def assemble_caption(first_line: str, following_lines) -> str:
    """Join a caption's continuation lines until a blank line or the next figure label."""
    parts = [first_line.strip()]
    for ln in following_lines:
        s = (ln or "").strip()
        if not s:
            break
        if _FIG_LABEL.match(s):
            break
        parts.append(s)
    return " ".join(p for p in parts if p)


def complete_caption(record, *, page_text: str | None = None) -> str:
    """Recover the full caption for a figure-bearing EvidenceRecord.

    Falls back to the (possibly truncated) first line when no page text is supplied.
    """
    meta = getattr(record, "metadata", {}) or {}
    first = (meta.get("caption") or "").strip()
    if not page_text:
        return first

    lines = page_text.splitlines()
    idx = None
    if first:
        for i, ln in enumerate(lines):
            if ln.strip() == first:
                idx = i
                break
    if idx is None:
        for i, ln in enumerate(lines):
            if _FIG_LABEL.match(ln.strip()):
                idx = i
                break
    if idx is None:
        return first
    return assemble_caption(lines[idx], lines[idx + 1:])


def relevance_line(claim_text: str, citation: str) -> str:
    """One neutral sentence linking the figure to its claim + source."""
    short = (claim_text or "").strip()
    if len(short) > 80:
        short = short[:77].rsplit(" ", 1)[0] + "..."
    if short:
        short = short[0].lower() + short[1:]
    cite = f" [{citation}]" if citation else ""
    return f"Relevant to {short}{cite}".strip()
