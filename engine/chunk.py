from dataclasses import dataclass
from typing import Optional


@dataclass
class Chunk:
    id: str
    book: str
    chapter: Optional[str]
    page: int
    text: str


def chunk_page(record, max_words, overlap):
    words = record.text.split()
    if not words:
        return []
    step = max(1, max_words - overlap)
    chunks = []
    idx = 0
    start = 0
    while start < len(words):
        text = " ".join(words[start:start + max_words])
        chunks.append(Chunk(
            id=f"{record.book}::p{record.page}::{idx}",
            book=record.book,
            chapter=record.chapter,
            page=record.page,
            text=text,
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
