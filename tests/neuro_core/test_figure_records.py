"""Wiring the per-figure crop into ingest: in crop mode a figure page yields one
FigurePlate per figure, and `figure_records` flattens them into per-plate dicts for the
visual index. Default (no crop) keeps the whole-page behavior unchanged."""

import os

import fitz
import pytest

from engine.ingest import extract_pages, figure_records


def _gray(side=300):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, side, side))
    pix.clear_with(180)
    return pix


@pytest.fixture
def two_figure_pdf(tmp_path):
    path = tmp_path / "Two Figure Atlas.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(45, 60, 285, 300), pixmap=_gray())
    page.insert_textbox(fitz.Rect(45, 310, 285, 380),
                        "Figure 1: First widget anatomy showing the alpha structure "
                        "and its relationship to the surrounding gamma corridor.",
                        fontsize=9)
    page.insert_image(fitz.Rect(330, 60, 560, 300), pixmap=_gray())
    page.insert_textbox(fitz.Rect(330, 310, 560, 380),
                        "Figure 2: Second widget anatomy showing the beta structure.",
                        fontsize=9)
    doc.new_page().insert_text((72, 72), "Plain text page with no imagery")
    doc.save(path)
    doc.close()
    return path


def test_extract_pages_crop_emits_per_figure_plates(two_figure_pdf, tmp_path):
    recs = extract_pages(two_figure_pdf, render=True, assets_dir=tmp_path, dpi=100,
                         figure_crop=True)
    fig_pages = [r for r in recs if r.has_figure]
    assert len(fig_pages) == 1
    plates = fig_pages[0].figures
    assert len(plates) == 2
    caps = " ".join((p.caption or "") for p in plates)
    assert "alpha" in caps and "beta" in caps
    for pl in plates:
        assert os.path.isfile(pl.figure_path)


def test_figure_records_flattens_to_one_per_plate(two_figure_pdf, tmp_path):
    recs = extract_pages(two_figure_pdf, render=True, assets_dir=tmp_path, dpi=100,
                         figure_crop=True)
    figs = figure_records(recs)
    assert len(figs) == 2
    assert {"book", "page", "figure_path", "caption", "bbox"} <= set(figs[0].keys())
    assert all(f["book"] == "Two Figure Atlas" for f in figs)


def test_extract_pages_default_is_whole_page(two_figure_pdf, tmp_path):
    recs = extract_pages(two_figure_pdf, render=True, assets_dir=tmp_path, dpi=100)
    page = [r for r in recs if r.has_figure][0]
    assert page.figures == []                              # no per-figure plates
    assert page.figure_path and page.figure_path.endswith(".png")
    assert "_f" not in os.path.basename(page.figure_path)  # whole page, not a crop
    # whole-page mode emits no per-plate figure records
    assert figure_records(recs) == []
