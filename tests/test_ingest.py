# tests/test_ingest.py
from engine.ingest import extract_pages, coverage_report


def test_extract_pages_text_and_chapters(tiny_pdf):
    recs = extract_pages(tiny_pdf)
    assert len(recs) == 4
    assert recs[0].book == "Sample Book"
    assert recs[0].page == 1
    assert "alpha" in recs[0].text
    # TOC: pages 1-2 Introduction, pages 3-4 Methods
    assert recs[0].chapter == "Introduction"
    assert recs[1].chapter == "Introduction"
    assert recs[2].chapter == "Methods"
    assert recs[3].chapter == "Methods"


def test_coverage_report(tiny_pdf):
    rep = coverage_report(tiny_pdf.parent)
    assert "Sample Book" in rep
    assert rep["Sample Book"]["pages"] == 4
    assert rep["Sample Book"]["pages_with_text"] == 4
    assert rep["Sample Book"]["coverage"] == 1.0
