import re
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


# A real medical-chapter bookmark in this corpus looks like "1 - History",
# "25 - Positioning for Spine Surgery", "300 - Radiosurgery…": a leading chapter
# number, a hyphen/en-dash, then a title. Used to anchor the contamination boundary
# (where the medical content ends), NOT to filter chapter labels — most textbooks in
# the corpus (Greenberg/Rhoton/Schmidek/NeuroICU) don't number chapters this way.
_MEDICAL_CHAPTER = re.compile(r"^\s*\d+\s*[-–]\s*\S")

# Contamination signals. A scraped Youmans PDF in this corpus has THREE copies of David
# Icke's "Perceptions of a Renegade Mind" appended after the medical content; Icke numbers
# chapters "Chapter N:" (colon), distinct from Youmans' "N - Title" (dash). The book-title
# match is zero-false-positive; the colon-chapter match is only trusted past the medical
# content (see _classify_toc) so it can't truncate a clean book.
_ICKE_CHAPTER = re.compile(r"^Chapter \d+:")

# Front-matter / structural bookmarks that are not chapter content. Dropped from chapter
# labels so they don't blanket the pages after them (e.g. "DEDICATION" → ~70 pages until
# chapter 1). Lowercased prefix match — zero false positives across the corpus.
# (Deliberately excludes "Introduction"/"Methods", which are legitimate chapter titles.)
_FRONT_MATTER_PREFIXES = (
    "copyright", "dedication", "contents", "table of contents", "title page",
    "contributors", "preface", "acknowledgment", "acknowledgement",
    "foreword", "index", "bibliography",
)

# "cover"-family bookmarks are matched EXACTLY (not as a prefix) so legitimate medical
# titles such as "Covered Stent Technique" or "Coverage of the scalp defect" are not
# swept up as front matter.
_FRONT_MATTER_EXACT = ("cover", "cover page", "front youmans cover")


def _is_medical_chapter(title) -> bool:
    """True only for the numbered "<n> - <title>" medical-chapter pattern."""
    return bool(_MEDICAL_CHAPTER.match((title or "").strip()))


def _is_front_matter(title) -> bool:
    t = (title or "").strip().lower()
    if t in _FRONT_MATTER_EXACT:
        return True
    return any(t.startswith(p) for p in _FRONT_MATTER_PREFIXES)


def _is_random_token(title) -> bool:
    """A long whitespace-free token *containing a digit* is a garbage bookmark, not a
    chapter title (e.g. "5yk4n23ycnpq9lc2A5dqvlhvrs2rhdbs9c6jz5gnc3xpr788fm4zwd2").

    Slash-joined section titles ("Laminotomy/Foraminotomy/Discectomy",
    "INDICATIONS/CONTRAINDICATIONS") and purely-alphabetic run-on tokens are real
    medical labels in other corpus books, so they are explicitly kept: a slash or the
    absence of any digit means "not random"."""
    t = (title or "").strip()
    if " " in t or "/" in t or _is_medical_chapter(t):
        return False
    return len(t) > 25 and any(ch.isdigit() for ch in t)


def _classify_toc(doc):
    """Classify the PDF table of contents into chapter labels + a content boundary.

    Returns ``(entries, content_end)`` where ``entries`` is the sorted
    ``(start_page_1based, title)`` list kept for chapter labelling (contamination,
    front-matter and garbage bookmarks dropped), and ``content_end`` is the 1-based start
    page of the first contamination bookmark past the medical content — the page at/after
    which the book stops being medical content — or ``None`` if there is no such boundary.
    """
    raw = []
    for _level, title, page in doc.get_toc():
        if page and page > 0:
            raw.append((page, (title or "").strip()))
    raw.sort(key=lambda e: e[0])

    medical_pages = [pg for pg, t in raw if _is_medical_chapter(t)]
    last_medical = max(medical_pages) if medical_pages else None

    content_end = None
    for pg, t in raw:
        # Both contamination signals are only trusted once we are past the last medical
        # chapter: a clean book that happens to use "Chapter N:" is safe, and a stray
        # "renegade mind" bookmark *before* the medical content can't truncate the book.
        past_medical = last_medical is not None and pg > last_medical
        is_renegade = "renegade mind" in t.lower() and past_medical
        is_icke = bool(_ICKE_CHAPTER.match(t)) and past_medical
        if is_renegade or is_icke:
            content_end = pg
            break

    # Chapter-label entries: drop the whole contamination region (everything at/after the
    # boundary, which is excluded from indexing anyway) plus front-matter and garbage
    # bookmarks. A clean book (content_end is None) keeps all of its labels.
    entries = [
        (pg, t) for pg, t in raw
        if (content_end is None or pg < content_end)
        and not _is_front_matter(t)
        and not _is_random_token(t)
    ]
    return entries, content_end


def _chapter_for_page(entries, page, *, max_gap: int = 120):
    """The chapter label for a page, or ``None`` when the TOC can't actually identify it.

    Assigns the nearest preceding bookmark — but if that bookmark starts more than
    ``max_gap`` pages back, the sparse TOC cannot tell us the chapter (huge un-bookmarked
    gaps would otherwise inherit one distant label), so return ``None`` ("unknown
    chapter"). Honest unknown beats a confidently-wrong distant label.
    """
    chapter = None
    chapter_start = None
    for start, title in entries:
        if start <= page:
            chapter = title
            chapter_start = start
        else:
            break
    if chapter_start is not None and page - chapter_start > max_gap:
        return None
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
    entries, content_end = _classify_toc(doc)
    records = []
    for i in range(len(doc)):
        pageno = i + 1
        # Drop non-medical contamination (e.g. the appended David Icke book) so it is
        # never indexed as medical content. Data-driven boundary, not a hardcoded page.
        if content_end is not None and pageno >= content_end:
            continue
        page = doc[i]
        text = page.get_text().strip()
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


MIN_TEXT_COVERAGE = 0.6  # below this, treat the PDF as scanned (no usable text layer)


def _probe_verdict(coverage, pages, min_coverage=MIN_TEXT_COVERAGE):
    """Pure go/no-go decision for a candidate corpus PDF."""
    if pages == 0:
        return False, "no pages extracted (unreadable or empty PDF)"
    if coverage < min_coverage:
        return False, (f"text coverage {coverage:.2f} < {min_coverage:.2f} — likely scanned "
                       "(no text layer); this pipeline does not OCR, indexing yields empty chunks")
    return True, f"text coverage {coverage:.2f} OK"


def probe_book(pdf_path, min_coverage=MIN_TEXT_COVERAGE):
    """Cheap preflight (no render, no GPU) before an expensive index build.

    Encodes the #1 textbook-integration failure mode: silently indexing a scanned book
    that has no text layer (the pipeline does not OCR, so it would yield empty chunks).
    Returns a dict with the coverage stats plus an ``ok``/``reason`` verdict.
    """
    recs = extract_pages(pdf_path, render=False)
    cov = coverage_from_records(recs)
    book = next(iter(cov), Path(pdf_path).stem)
    s = cov.get(book, {"pages": 0, "pages_with_text": 0, "coverage": 0.0,
                       "pages_with_figures": 0})
    chapters = len({r.chapter for r in recs if getattr(r, "chapter", None)})
    ok, reason = _probe_verdict(s["coverage"], s["pages"], min_coverage)
    return {"book": book, "pages": s["pages"], "pages_with_text": s["pages_with_text"],
            "coverage": s["coverage"], "pages_with_figures": s["pages_with_figures"],
            "chapters": chapters, "ok": ok, "reason": reason}
