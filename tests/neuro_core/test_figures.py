import fitz

from neuro_core.figures import (
    figure_area_fraction, detect_figure, extract_caption,
    page_figure_info, render_page_png,
)


def test_detect_figure_true_on_image_page(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    assert figure_area_fraction(doc[0]) > 0.3
    assert detect_figure(doc[0], area_threshold=0.1) is True
    doc.close()


def test_detect_figure_false_on_text_page(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    assert figure_area_fraction(doc[1]) == 0.0
    assert detect_figure(doc[1], area_threshold=0.1) is False
    doc.close()


def test_extract_caption(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    assert extract_caption(doc[0]) == "Figure 1-1: Lateral view of the cavernous sinus"
    assert extract_caption(doc[1]) is None
    doc.close()


def test_page_figure_info(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    info = page_figure_info(doc[0], area_threshold=0.1)
    assert info.has_figure is True
    assert "cavernous sinus" in info.caption
    info2 = page_figure_info(doc[1], area_threshold=0.1)
    assert info2.has_figure is False
    assert info2.caption is None
    doc.close()


def test_render_page_png_creates_and_is_idempotent(pdf_with_figure, tmp_path):
    doc = fitz.open(pdf_with_figure)
    out = tmp_path / "figs" / "Atlas Book" / "p0001.png"
    p = render_page_png(doc[0], dpi=120, out_path=out)
    assert p.exists() and p.stat().st_size > 0
    mtime = p.stat().st_mtime_ns
    # second call must NOT re-render (resumable behavior)
    render_page_png(doc[0], dpi=120, out_path=out)
    assert p.stat().st_mtime_ns == mtime
    doc.close()
