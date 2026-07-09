from dataclasses import dataclass
from typing import Optional


@dataclass
class Chunk:
    id: str
    book: str
    chapter: Optional[str]
    page: int
    text: str
    printed_page: Optional[str] = None
    has_figure: bool = False
    caption: Optional[str] = None
    figure_path: Optional[str] = None


# A page with fewer than this many words and no figure/caption is a running-head, title, or
# table-of-contents fragment (e.g. "History of Spine Surgery 17.e1 1"), not indexable content.
# Dropping it removes the sub-threshold chunks the bibliography line-strip can otherwise leave
# behind. Figure/caption pages are kept regardless — their caption IS the content.
MIN_PAGE_WORDS = 20


def chunk_page(record, max_words, overlap):
    words = record.text.split()
    if not words:
        return []
    if (len(words) < MIN_PAGE_WORDS
            and not (record.caption or "").strip()
            and not record.has_figure):
        return []
    step = max(1, max_words - overlap)
    # Fold the figure caption into the chunk's indexed text so the plate that NAMES the queried
    # anatomy is reachable by both the dense and the BM25 lane (previously the caption lived only
    # in a separate column that neither searched). Appended once per chunk of a figure page.
    caption = (record.caption or "").strip()
    caption_suffix = f"\n\n{caption}" if caption else ""
    chunks = []
    idx = 0
    start = 0
    while start < len(words):
        text = " ".join(words[start:start + max_words]) + caption_suffix
        chunks.append(Chunk(
            id=f"{record.book}::p{record.page}::{idx}",
            book=record.book,
            chapter=record.chapter,
            page=record.page,
            text=text,
            printed_page=record.printed_page,
            has_figure=record.has_figure,
            caption=record.caption,
            figure_path=record.figure_path,
        ))
        idx += 1
        if start + max_words >= len(words):
            break
        start += step
    return chunks


def chunk_pages(records, max_words, overlap):
    out = []
    for rec in records:
        out.extend(chunk_page(rec, max_words, overlap))
    return out
