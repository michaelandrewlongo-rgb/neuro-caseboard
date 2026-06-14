"""Shared evidence model: a neutral, typed reference to one piece of cited evidence (a textbook
citation or a figure), used as the lingua franca for cross-feature flows. Q&A's Citation/Figure
and the board's FigureItem adapt to it at the app boundary; the engines are untouched."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRef:
    book: str = ""
    page: int | None = None
    chapter: str = ""
    citation: str = ""
    figure_path: str | None = None
    caption: str = ""
    score: float | None = None
    source: str = ""

    @property
    def key(self) -> str:
        """Stable cross-link identity: figures by page-image path, citations by (book, page)."""
        if self.figure_path:
            return f"fig:{self.figure_path}"
        return f"cite:{self.book}|{self.page}"


def _cite_str(book, page) -> str:
    return f"{book}, p.{page}" if book else ""


def from_citation(c) -> EvidenceRef:
    return EvidenceRef(book=c.book, page=c.page, chapter=getattr(c, "chapter", "") or "",
                       citation=_cite_str(c.book, c.page), source="qa")


def from_figure(f) -> EvidenceRef:
    return EvidenceRef(book=f.book, page=f.page, chapter=getattr(f, "chapter", "") or "",
                       citation=_cite_str(f.book, f.page), figure_path=f.image_path,
                       caption=f.caption or "", source="qa")


def from_figure_item(fi) -> EvidenceRef:
    return EvidenceRef(citation=fi.citation or "", figure_path=fi.image_path,
                       caption=fi.caption or "", source="board")


def record(store: dict, refs, label: str) -> None:
    """Add `label` to the set of features each ref's key appears in."""
    for r in refs:
        store.setdefault(r.key, set()).add(label)


def other_features(store: dict, key: str, label: str) -> list[str]:
    """Feature labels (other than `label`) that this key appears in, sorted."""
    return sorted(lbl for lbl in store.get(key, set()) if lbl != label)
