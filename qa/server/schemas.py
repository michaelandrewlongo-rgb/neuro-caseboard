from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from pydantic import BaseModel

if TYPE_CHECKING:  # avoid importing the heavy engine stack at runtime
    from engine.query import QueryResult


class AskRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    n: int
    book: str
    chapter: str
    page: int


class FigureOut(BaseModel):
    source_n: int
    book: str
    page: int
    caption: str
    url: str


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut] = []
    figures: list[FigureOut] = []


def _figure_url(image_path: str, assets_dir) -> str:
    """Build the /figures URL for a figure. The path is kept RELATIVE to assets_dir,
    because figure files live in per-book subdirectories and their filenames collide
    across books (every book has a p0001.png) — the bare filename is ambiguous and
    would 404. The relative path is percent-encoded so spaces in book names stay valid.
    Falls back to the bare filename if image_path is unexpectedly outside assets_dir."""
    p = Path(image_path)
    try:
        rel = p.relative_to(assets_dir)
    except ValueError:
        rel = Path(p.name)
    return "/figures/" + quote(str(rel))


def to_response(result: QueryResult, assets_dir) -> AskResponse:
    """Map an engine QueryResult to the wire schema. Each figure's local image_path
    becomes a /figures/<book>/<file> URL (relative to assets_dir) the phone can fetch."""
    return AskResponse(
        answer=result.answer,
        citations=[CitationOut(n=c.n, book=c.book, chapter=c.chapter, page=c.page)
                   for c in result.citations],
        figures=[FigureOut(source_n=f.source_n, book=f.book, page=f.page,
                           caption=f.caption, url=_figure_url(f.image_path, assets_dir))
                 for f in result.figures],
    )
