"""Per-figure plate cropping + caption association (the upstream lever for figure
relevance). A page can carry several distinct figures; the visual lane must embed one
CROPPED plate per figure (not the whole text-dominated page), each tagged with its own
full, multi-line caption."""

import fitz
import pytest

from neuro_core.figures import (
    figure_plate_bboxes,
    extract_figure_plates,
    extract_caption_for_bbox,
    crop_plate_png,
    FigurePlate,
)


def _gray_pixmap(side=300):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, side, side))
    pix.clear_with(180)
    return pix


@pytest.fixture
def two_figure_pdf(tmp_path):
    """1 page, A4, with TWO separated raster figures (left + right), each with its own
    multi-line caption block below it; sized so each plate clears the area floor."""
    path = tmp_path / "Two Figure Atlas.pdf"
    doc = fitz.open()
    page = doc.new_page()  # A4 595x842
    # Left figure + caption
    page.insert_image(fitz.Rect(45, 60, 285, 300), pixmap=_gray_pixmap())
    page.insert_textbox(
        fitz.Rect(45, 310, 285, 380),
        "Figure 1: First widget anatomy showing the alpha structure and its "
        "relationship to the surrounding gamma corridor.",
        fontsize=9)
    # Right figure + caption (horizontal gap > merge gap so they stay distinct plates)
    page.insert_image(fitz.Rect(330, 60, 560, 300), pixmap=_gray_pixmap())
    page.insert_textbox(
        fitz.Rect(330, 310, 560, 380),
        "Figure 2: Second widget anatomy showing the beta structure.",
        fontsize=9)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def tiny_image_pdf(tmp_path):
    """A page whose only raster image is too small to be a real figure plate."""
    path = tmp_path / "Tiny.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(50, 50, 95, 95), pixmap=_gray_pixmap(40))
    doc.save(path)
    doc.close()
    return path


def test_figure_plate_bboxes_separates_two_figures(two_figure_pdf):
    doc = fitz.open(two_figure_pdf)
    plates = figure_plate_bboxes(doc[0], area_threshold=0.1)
    assert len(plates) == 2
    doc.close()


def test_extract_figure_plates_crops_smaller_than_page(two_figure_pdf, tmp_path):
    doc = fitz.open(two_figure_pdf)
    page = doc[0]
    plates = extract_figure_plates(page, area_threshold=0.1, dpi=100,
                                   assets_dir=tmp_path, book="Atlas", pageno=7)
    assert len(plates) == 2
    full = page.get_pixmap(dpi=100)
    for pl in plates:
        assert isinstance(pl, FigurePlate)
        crop = fitz.Pixmap(pl.figure_path)
        # a cropped plate must be materially smaller than the whole page
        assert crop.width < full.width
        assert crop.height < full.height
    doc.close()


def test_caption_associated_per_plate(two_figure_pdf, tmp_path):
    doc = fitz.open(two_figure_pdf)
    plates = extract_figure_plates(doc[0], area_threshold=0.1, dpi=100,
                                   assets_dir=tmp_path, book="Atlas", pageno=1)
    caps = sorted((pl.caption or "") for pl in plates)
    assert any("alpha" in c for c in caps)
    assert any("beta" in c for c in caps)
    # left figure's caption must not be the right figure's
    by_x = sorted(plates, key=lambda p: p.bbox[0])
    assert "alpha" in (by_x[0].caption or "")
    assert "beta" in (by_x[1].caption or "")
    doc.close()


def test_caption_is_full_not_first_line_only(two_figure_pdf):
    doc = fitz.open(two_figure_pdf)
    page = doc[0]
    plates = figure_plate_bboxes(page, area_threshold=0.1)
    left = min(plates, key=lambda r: r.x0)
    cap = extract_caption_for_bbox(page, tuple(left))
    # full multi-line caption, not truncated at the first physical line
    assert "alpha structure" in cap
    assert "gamma corridor" in cap
    doc.close()


def test_extract_figure_plates_idempotent(two_figure_pdf, tmp_path):
    doc = fitz.open(two_figure_pdf)
    page = doc[0]
    p1 = extract_figure_plates(page, area_threshold=0.1, dpi=100,
                               assets_dir=tmp_path, book="Atlas", pageno=3)
    mtimes = {pl.figure_path: __import__("os").stat(pl.figure_path).st_mtime_ns
              for pl in p1}
    p2 = extract_figure_plates(page, area_threshold=0.1, dpi=100,
                               assets_dir=tmp_path, book="Atlas", pageno=3)
    for pl in p2:
        assert __import__("os").stat(pl.figure_path).st_mtime_ns == mtimes[pl.figure_path]
    doc.close()


def test_no_plates_for_tiny_image(tiny_image_pdf, tmp_path):
    doc = fitz.open(tiny_image_pdf)
    plates = extract_figure_plates(doc[0], area_threshold=0.1, dpi=100,
                                   assets_dir=tmp_path, book="Tiny", pageno=1)
    assert plates == []
    doc.close()


def test_extract_caption_truncates_long_legend(tmp_path):
    """A figure caption block often runs straight into a multi-paragraph legend (3000+
    chars). The returned caption must be the caption SENTENCE, not the whole legend —
    a bloated caption poisons downstream region guards with stray substrings (the real
    regression: 'disc dissector' in a pituitary legend matched the spine guard)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(60, 60, 300, 300), pixmap=_gray_pixmap())
    legend = ("Figure 9. The pituitary gland and sella turcica. "
              + "Lorem ipsum dolor sit amet. " * 40 + "A disc dissector is used here.")
    page.insert_textbox(fitz.Rect(60, 310, 545, 800), legend, fontsize=8)
    cap = extract_caption_for_bbox(page, (60, 60, 300, 300))
    assert cap.startswith("Figure 9. The pituitary gland and sella turcica.")
    assert "disc dissector" not in cap       # contaminating legend tail truncated away
    assert len(cap) < 400
    doc.close()


def test_crop_plate_png_skips_offpage_bbox(two_figure_pdf, tmp_path):
    """Regression: Fukushima p22 has an image placed entirely off the left edge
    (bbox x = -332..-47). Clamped to the page it is zero-width -> a 0-px pixmap that
    crashes PNG save ('Invalid bandwriter header'). crop_plate_png must skip it, not raise."""
    doc = fitz.open(two_figure_pdf)
    page = doc[0]
    out = crop_plate_png(page, (-332.5, 516.6, -47.3, 730.5), dpi=100,
                         out_path=tmp_path / "x.png")
    assert out is None
    assert not (tmp_path / "x.png").exists()
    # a bbox entirely below the page is likewise skipped (inverted intersection)
    assert crop_plate_png(page, (50, 5000, 200, 5200), dpi=100,
                          out_path=tmp_path / "y.png") is None
    doc.close()
