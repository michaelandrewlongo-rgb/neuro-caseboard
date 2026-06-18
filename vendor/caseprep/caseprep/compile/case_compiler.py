"""Compiler: transform audited claims into a surgeon-facing case board.

Takes an AuditedManifest and produces a clean, actionable markdown dossier.
The primary surface is a case board — not an audit ledger.  Evidence and
off-target claims are surfaced in an expandable appendix, not inline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from caseprep.core.contracts import SlotConfidence


# ── data contracts ───────────────────────────────────────────────────────────


@dataclass
class CompiledSection:
    """One section of the case board."""

    heading: str
    body: str
    source_cards: list[str] = field(default_factory=list)  # question text refs
    confidence: Optional[SlotConfidence] = None
    confidence_band: str = "" # NEW
    is_primary: bool = True  # primary surface vs appendix


@dataclass
class CompiledBoard:
    """Complete surgeon-facing case board."""

    title: str
    sections: list[CompiledSection] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"# {self.title}", ""]
        for sec in self.sections:
            if sec.is_primary:
                lines.append(f"## {sec.heading}")
                lines.append("")
                lines.append(sec.body.strip())
                lines.append("")
        # Appendix
        appendix_sections = [s for s in self.sections if not s.is_primary]
        if appendix_sections:
            lines.append("---")
            lines.append("")
            lines.append("## Evidence Appendix *(expand for provenance)*")
            lines.append("")
            for sec in appendix_sections:
                lines.append(f"### {sec.heading}")
                lines.append("")
                lines.append(sec.body.strip())
                lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "sections": [
                {
                    "heading": s.heading,
                    "body": s.body,
                    "source_cards": s.source_cards,
                    "is_primary": s.is_primary,
                }
                for s in self.sections
            ],
        }


# ── rendering helpers ────────────────────────────────────────────────────────


def _status_label(status: str) -> str:
    return {
        "supported": "✓",
        "needs_review": "VERIFY",
        "off_target": "✗ (off-target evidence)",
        "no_evidence": "— (no evidence)",
    }.get(status, "?")


def _render_card_line(card) -> str:
    """Render one audited card as a markdown line."""
    label = _status_label(card.audit_status)
    
    confidence_marker = ""
    if hasattr(card, 'confidence') and card.confidence is not None:
        band = _confidence_band(card.confidence)
        markers = {"high": " 🟢", "medium": " 🟡", "low": " 🔴"}
        confidence_marker = markers.get(band, "")
    
    return f"- {label} {card.question}{confidence_marker} — *{card.why_it_matters}*"


def _brief_card_line(card) -> str:
    """Shorter rendering for appendix."""
    label = _status_label(card.audit_status)
    q = card.question[:120]
    w = card.why_it_matters[:80]
    return f"- {label} {q} — {w}"



def _section_intro(heading: str) -> str:
    """Render section intro line from heading name."""
    intros = {
        "Anatomy at Risk": (
            "Structures that must be identified, preserved, or monitored during this approach."
        ),
        "Operative Plan": (
            "Critical steps, decision points, and stop criteria for this procedure."
        ),
        "Risk and Rescue": (
            "Expected and catastrophic complications with specific rescue sequences."
        ),
    }
    desc = intros.get(heading, "")
    if desc:
        return f"**{heading}**: *{desc}*\n\n"
    return f"**{heading}**\n\n"


def _confidence_band(confidence) -> str:
    """Map normalized confidence to band label."""
    if confidence is None:
        return ""
    try:
        nc = confidence.normalized_confidence
    except AttributeError:
        return ""
    if nc >= 0.85:
        return "high"
    elif nc >= 0.50:
        return "medium"
    else:
        return "low"


# ── public API ───────────────────────────────────────────────────────────────


def _render_board_pearls(pearls: list, *, top_n: int = 5) -> str:
    """Render board card hits as a compact reference section."""
    if not pearls:
        return ""
    lines = [
        "**High-yield board pearls semantically matched to this case:**\n",
    ]
    for i, p in enumerate(pearls[:top_n], 1):
        sim_str = f" ({p.similarity:.2f})" if hasattr(p, "similarity") else ""
        q = (p.question or "—")[:150]
        a = (p.answer or "—")[:150]
        tags_str = ", ".join(p.tags[:4]) if p.tags else ""
        lines.append(f"{i}. **Q:** {q}{sim_str}")
        lines.append(f"   **A:** {a}")
        if tags_str:
            lines.append(f"   *Tags: {tags_str}*")
        lines.append("")
    return "\n".join(lines)


def compile_board(
    audited_manifest,  # AuditedManifest
    *,
    topic: str = "",
    board_pearls: list | None = None,  # list[BoardCardRecord]
) -> CompiledBoard:
    """Compile audited claims into a surgeon-facing case board.

    Supported claims become primary guidance.  Needs-review claims become
    VERIFY prompts.  Off-target / no-evidence claims are quarantined to
    the appendix.

    If *board_pearls* is provided, a \"Board Pearls\" section is appended
    with the top semantically-matched ABNS flashcard hits.
    """
    # Group cards by target_file
    groups: dict[str, list] = {
        "03-anatomy-at-risk.md": [],
        "04-operative-plan.md": [],
        "05-risk-and-rescue.md": [],
    }
    for card in audited_manifest.cards:
        groups.setdefault(card.target_file, []).append(card)

    section_map = {
        "03-anatomy-at-risk.md": ("Anatomy at Risk", "anatomy"),
        "04-operative-plan.md": ("Operative Plan", "operative"),
        "05-risk-and-rescue.md": ("Risk and Rescue", "risk"),
    }

    sections: list[CompiledSection] = []

    for target_file, cards in groups.items():
        if not cards:
            continue
        heading, _ = section_map.get(target_file, (target_file, ""))

        primary_cards = [c for c in cards if c.audit_status in ("supported", "needs_review")]
        appendix_cards = [c for c in cards if c.audit_status in ("off_target", "no_evidence")]

        # ── primary section ──────────────────────────────────────────
        primary_lines = []
        intro = _section_intro(heading)
        if intro:
            primary_lines.append(f"{intro}\n")

        if not primary_cards:
            primary_lines.append("`needs input` — no validated claims available.")
        else:
            for card in primary_cards:
                primary_lines.append(_render_card_line(card))

        primary_lines.append("")
        primary_lines.append("*See appendix for evidence sources and off-target claims.*")

        sections.append(CompiledSection(
            heading=heading,
            body="\n".join(primary_lines),
            source_cards=[c.question for c in primary_cards],
            is_primary=True,
            confidence=primary_cards[0].confidence if len(primary_cards) == 1 else None,
            confidence_band=_confidence_band(
                primary_cards[0].confidence if primary_cards and hasattr(primary_cards[0], 'confidence') else None
            ),
        ))

        # ── appendix section ─────────────────────────────────────────
        if appendix_cards:
            appendix_lines = [f"*{len(appendix_cards)} cards flagged as off-target or lacking evidence:*\n"]
            for card in appendix_cards:
                appendix_lines.append(_brief_card_line(card))
                if card.audit_reason:
                    appendix_lines.append(f"  - Reason: {card.audit_reason}")
                if card.papers:
                    for p in card.papers[:2]:
                        appendix_lines.append(f"  - Source: {p.get('title', '')[:120]}")
            sections.append(CompiledSection(
                heading=f"{heading} — Quarantined",
                body="\n".join(appendix_lines),
                source_cards=[],
                is_primary=False,
                confidence_band=_confidence_band(
                    primary_cards[0].confidence if primary_cards and hasattr(primary_cards[0], 'confidence') else None
                ),
            ))

    # ── summary section ──────────────────────────────────────────────
    supported_count = sum(1 for c in audited_manifest.cards if c.audit_status == "supported")
    verify_count = sum(1 for c in audited_manifest.cards if c.audit_status == "needs_review")
    off_count = sum(1 for c in audited_manifest.cards if c.audit_status == "off_target")
    noev_count = sum(1 for c in audited_manifest.cards if c.audit_status == "no_evidence")

    summary = (
        f"**{supported_count}** claims supported by corpus evidence.  "
        f"**{verify_count}** need clinician verification.  "
        f"**{off_count}** off-target papers quarantined.  "
        f"**{noev_count}** had no retrievable evidence.\n\n"
        f"*Case: {topic}*"
    )

    sections.insert(0, CompiledSection(
        heading="Summary",
        body=summary,
        source_cards=[],
        is_primary=True,
    ))

    # ── confidence summary ────────────────────────────────────────────
    high = sum(1 for c in audited_manifest.cards 
               if hasattr(c, 'confidence') and c.confidence is not None
               and _confidence_band(c.confidence) == "high")
    medium = sum(1 for c in audited_manifest.cards 
                 if hasattr(c, 'confidence') and c.confidence is not None
                 and _confidence_band(c.confidence) == "medium")
    low = sum(1 for c in audited_manifest.cards 
              if hasattr(c, 'confidence') and c.confidence is not None
              and _confidence_band(c.confidence) == "low")
    
    if high + medium + low > 0:
        confidence_summary = (
            f"Confidence: **{high}** high 🟢, **{medium}** medium 🟡, **{low}** low 🔴\n\n"
        )
        # Append to the existing summary section's body
        sections[0].body = confidence_summary + sections[0].body

    # ── board pearls section ──────────────────────────────────────────
    if board_pearls:
        pearl_body = _render_board_pearls(board_pearls)
        if pearl_body:
            sections.append(CompiledSection(
                heading="Board Pearls (ABNS Review)",
                body=pearl_body,
                source_cards=[p.question for p in board_pearls[:5] if p.question],
                is_primary=True,
            ))

    return CompiledBoard(
        title=f"Case Board — {topic}" if topic else "Case Board",
        sections=sections,
    )
