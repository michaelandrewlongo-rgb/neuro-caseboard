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


def assemble_caption(first_line: str, following_lines, *, max_chars: int = 240) -> str:
    """Join a caption's continuation lines until a blank line or the next figure label.

    Textbook page text often has no blank line between a caption and the body paragraph,
    so the join is also bounded to ``max_chars`` and trimmed back to the last sentence end
    — this keeps the complete caption without absorbing the following body text."""
    parts = [first_line.strip()]
    for ln in following_lines:
        s = (ln or "").strip()
        if not s:
            break
        if _FIG_LABEL.match(s):
            break
        parts.append(s)
        if sum(len(p) + 1 for p in parts) >= max_chars:
            break
    cap = " ".join(p for p in parts if p)
    if len(cap) > max_chars:
        cut = cap[:max_chars]
        dot = cut.rfind(". ")
        cap = (cut[: dot + 1] if dot > 60 else cut.rsplit(" ", 1)[0] + " …")
    return cap


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
