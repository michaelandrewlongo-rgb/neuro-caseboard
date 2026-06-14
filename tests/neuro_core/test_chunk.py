# tests/test_chunk.py
from neuro_core.chunk import chunk_page, chunk_pages
from neuro_core.ingest import PageRecord


def _rec(text, page=1, book="B", chapter="C"):
    return PageRecord(book=book, page=page, text=text, chapter=chapter)


def test_short_page_one_chunk():
    chunks = chunk_page(_rec("alpha beta gamma"), max_words=600, overlap=80)
    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert chunks[0].book == "B"
    assert chunks[0].chapter == "C"
    assert chunks[0].id == "B::p1::0"
    assert chunks[0].text == "alpha beta gamma"


def test_long_page_splits_with_overlap():
    words = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_page(_rec(words), max_words=600, overlap=80)
    assert len(chunks) == 2
    # second chunk starts at 600 - 80 = 520
    assert chunks[1].text.split()[0] == "w520"
    assert all(c.page == 1 for c in chunks)
    assert {c.id for c in chunks} == {"B::p1::0", "B::p1::1"}


def test_empty_page_no_chunks():
    assert chunk_page(_rec(""), max_words=600, overlap=80) == []


def test_chunk_pages_concatenates():
    recs = [_rec("a b c", page=1), _rec("d e f", page=2)]
    chunks = chunk_pages(recs, max_words=600, overlap=80)
    assert [c.page for c in chunks] == [1, 2]


def test_chunks_carry_figure_attrs():
    rec = PageRecord(book="B", page=3, text="alpha beta", chapter="C",
                     has_figure=True, caption="Figure 3-1: x", figure_path="/p3.png")
    chunks = chunk_page(rec, max_words=600, overlap=80)
    assert chunks[0].has_figure is True
    assert chunks[0].caption == "Figure 3-1: x"
    assert chunks[0].figure_path == "/p3.png"
