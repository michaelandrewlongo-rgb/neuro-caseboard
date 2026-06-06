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


def test_extract_pages_sets_figure_fields(pdf_with_figure):
    recs = extract_pages(pdf_with_figure, area_threshold=0.1)
    assert recs[0].has_figure is True
    assert "cavernous sinus" in recs[0].caption
    assert recs[0].figure_path is None  # render=False by default
    assert recs[1].has_figure is False
    assert recs[1].caption is None


def test_extract_pages_renders_when_requested(pdf_with_figure, tmp_path):
    recs = extract_pages(pdf_with_figure, render=True, assets_dir=tmp_path,
                         dpi=120, area_threshold=0.1)
    assert recs[0].figure_path is not None
    from pathlib import Path
    assert Path(recs[0].figure_path).exists()
    assert recs[1].figure_path is None


def test_coverage_includes_figure_counts(pdf_with_figure):
    rep = coverage_report(pdf_with_figure.parent)
    assert rep["Atlas Book"]["pages_with_figures"] == 1
