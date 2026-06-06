from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import fitz  # PyMuPDF


@dataclass
class PageRecord:
    book: str
    page: int          # 1-based
    text: str
    chapter: Optional[str]


def _chapter_entries(doc):
    """Sorted (start_page_1based, title) from the PDF table of contents."""
    entries = []
    for _level, title, page in doc.get_toc():
        if page and page > 0:
            entries.append((page, title.strip()))
    entries.sort(key=lambda e: e[0])
    return entries


def _chapter_for_page(entries, page):
    chapter = None
    for start, title in entries:
        if start <= page:
            chapter = title
        else:
            break
    return chapter


def extract_pages(pdf_path):
    pdf_path = Path(pdf_path)
    book = pdf_path.stem
    doc = fitz.open(pdf_path)
    entries = _chapter_entries(doc)
    records = []
    for i in range(len(doc)):
        text = doc[i].get_text().strip()
        page = i + 1
        records.append(
            PageRecord(book=book, page=page, text=text,
                       chapter=_chapter_for_page(entries, page))
        )
    doc.close()
    return records


def iter_corpus(corpus_dir) -> Iterator[PageRecord]:
    for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
        for rec in extract_pages(pdf):
            yield rec


def coverage_report(corpus_dir):
    report = {}
    for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
        recs = extract_pages(pdf)
        total = len(recs)
        nonempty = sum(1 for r in recs if len(r.text) > 50)
        report[pdf.stem] = {
            "pages": total,
            "pages_with_text": nonempty,
            "coverage": round(nonempty / total, 3) if total else 0.0,
        }
    return report
