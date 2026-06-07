from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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


def to_response(result: QueryResult) -> AskResponse:
    """Map an engine QueryResult to the wire schema. Figure image_path (a local
    absolute path) becomes a /figures/<filename> URL the phone can fetch."""
    return AskResponse(
        answer=result.answer,
        citations=[CitationOut(n=c.n, book=c.book, chapter=c.chapter, page=c.page)
                   for c in result.citations],
        figures=[FigureOut(source_n=f.source_n, book=f.book, page=f.page,
                           caption=f.caption, url=f"/figures/{Path(f.image_path).name}")
                 for f in result.figures],
    )
