"""Report model for the unified case-board dossier.

Deliberately decoupled from caseprep's CompiledBoard: this is the corrected
presentation contract the renderers consume. Markers carry semantic status only
(evidence axis); there is no confidence axis (defect #2/#3 — dropped by design).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Status markers (evidence axis). The Unicode glyph renders via the embedded font in
# PDF; the ASCII token is the deterministic fallback (defect #1).
MARK = {"supported": "✓", "verify": "⚠"}        # ✓ , ⚠
ASCII_MARK = {"supported": "[OK]", "verify": "[VERIFY]"}
LEGEND_ITEMS = [
    ("supported", "corpus-supported"),
    ("verify", "needs clinician verification"),
]


@dataclass
class FigureItem:
    fig_id: str                       # stable label, e.g. "F1"
    image_path: str
    caption: str                      # complete caption (#7)
    citation: str = ""                # e.g. "Benzel Spine, p.592"
    relevance: str = ""               # subspecialty-neutral relevance line (#7)
    claim_ref: str | None = None      # short text of the claim it supports (#7 cross-link)


@dataclass
class Claim:
    text: str                         # claim / question, scrubbed (#5: separate from why)
    why: str = ""                     # rationale, rendered on its own indented line (#5)
    status: str = "supported"         # "supported" | "verify"
    sub_items: list[str] = field(default_factory=list)   # checkbox sub-items (#6)
    figure_ids: list[str] = field(default_factory=list)  # linked figures (#7 cross-link)
    raw: str | None = None            # original source text used for dedup (#9)

    @property
    def dedup_text(self) -> str:
        return self.raw if self.raw is not None else self.text


@dataclass
class Section:
    heading: str
    intro: str = ""
    claims: list[Claim] = field(default_factory=list)
    figures: list[FigureItem] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)   # populated by dedup (#9)


@dataclass
class EvidenceSummary:
    """One clean evidence-disposition partition (defect #2: no second axis to
    contradict it). supported + to_verify + quarantined == total cards."""

    supported: int = 0       # corpus-supported
    to_verify: int = 0       # needs_review + no corpus match -> clinician verifies
    quarantined: int = 0     # off-target retrievals, moved to the appendix


@dataclass
class AppendixEntry:
    heading: str
    items: list[str] = field(default_factory=list)     # quarantined claim lines
    sources: list[str] = field(default_factory=list)   # evidence source citations


@dataclass
class Appendix:
    entries: list[AppendixEntry] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(e.items or e.sources for e in self.entries)


@dataclass
class Dossier:
    title: str
    summary: EvidenceSummary
    sections: list[Section] = field(default_factory=list)
    appendix: Appendix = field(default_factory=Appendix)
