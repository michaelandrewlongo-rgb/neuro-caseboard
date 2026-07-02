from neuro_core.chunk_strategies import _selfcheck, chunk_records
from neuro_core.ingest import PageRecord


def _rec(text, page, chapter="C1"):
    return PageRecord(book="B", page=page, text=text, chapter=chapter)


def test_selfcheck():
    # exercises page-barrier / chapter-cross / sentence-atoms / overlap-carry / oversized-atom
    _selfcheck()


def test_page_barrier_vs_chapter_cross():
    """The core mechanism behind the benchmark: page-anchored never crosses a page boundary;
    chapter packs across pages within a chapter."""
    recs = [_rec("one two three", 1), _rec("four five six", 2)]
    assert len(chunk_records(recs, "page", 100, 0)) == 2      # page barrier keeps them apart
    assert len(chunk_records(recs, "chapter", 100, 0)) == 1   # chapter merges across pages
