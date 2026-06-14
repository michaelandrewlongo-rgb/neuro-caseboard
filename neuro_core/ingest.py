from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import fitz  # PyMuPDF

from neuro_core.figures import page_figure_info, render_page_png, extract_figure_plates


@dataclass
class PageRecord:
    book: str
    page: int          # 1-based
    text: str
    chapter: Optional[str]
    has_figure: bool = False
    caption: Optional[str] = None
    figure_path: Optional[str] = None
    # Per-figure cropped plates (crop mode only); empty in whole-page mode.
    figures: list = field(default_factory=list)


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


def extract_pages(pdf_path, render=False, assets_dir=None, dpi=160,
                  area_threshold=0.1, figure_crop=False):
    """Extract page text + figures. With ``figure_crop`` each figure page yields one
    cropped plate per figure (``PageRecord.figures``, full per-plate captions) for the
    visual lane; the chunk's ``figure_path`` points at the first plate. Without it (the
    default) a figure page renders to a single whole-page PNG, unchanged."""
    pdf_path = Path(pdf_path)
    book = pdf_path.stem
    doc = fitz.open(pdf_path)
    entries = _chapter_entries(doc)
    records = []
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text().strip()
        pageno = i + 1
        info = page_figure_info(page, area_threshold)
        figure_path = None
        plates = []
        if info.has_figure and render and assets_dir is not None:
            if figure_crop:
                plates = extract_figure_plates(
                    page, area_threshold, dpi=dpi, assets_dir=assets_dir,
                    book=book, pageno=pageno)
            if plates:
                figure_path = plates[0].figure_path     # chunk links to the first plate
            else:                                         # whole-page (default / vector-only)
                out = Path(assets_dir) / book / f"p{pageno:04d}.png"
                render_page_png(page, dpi, out)
                figure_path = str(out)
        records.append(
            PageRecord(book=book, page=pageno, text=text,
                       chapter=_chapter_for_page(entries, pageno),
                       has_figure=info.has_figure, caption=info.caption,
                       figure_path=figure_path, figures=plates)
        )
    doc.close()
    return records


def figure_records(records):
    """Flatten per-page cropped plates into one dict per plate for the visual index
    (book, chapter, page, figure_path, full caption, bbox). Whole-page records contribute
    nothing — their visual lane is built from the page render via the chunks table."""
    out = []
    for r in records:
        for pl in (r.figures or []):
            out.append({"book": r.book, "chapter": r.chapter, "page": r.page,
                        "figure_path": pl.figure_path, "caption": pl.caption or "",
                        "bbox": pl.bbox})
    return out


def iter_corpus(corpus_dir) -> Iterator[PageRecord]:
    for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
        for rec in extract_pages(pdf):
            yield rec


def coverage_from_records(records):
    """Coverage stats grouped by book, computed from already-extracted records."""
    by_book = {}
    for r in records:
        by_book.setdefault(r.book, []).append(r)
    report = {}
    for book, recs in by_book.items():
        total = len(recs)
        nonempty = sum(1 for r in recs if len(r.text) > 50)
        report[book] = {
            "pages": total,
            "pages_with_text": nonempty,
            "coverage": round(nonempty / total, 3) if total else 0.0,
            "pages_with_figures": sum(1 for r in recs if r.has_figure),
        }
    return report


def coverage_report(corpus_dir):
    return coverage_from_records(list(iter_corpus(corpus_dir)))
