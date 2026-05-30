from __future__ import annotations
import base64
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.renderers.briefing_html import render_briefing_html


def _store(tmp_img):
    return [FigureRecord("image_bank", "1", ["aspects"], "ASPECTS template",
                         str(tmp_img), None, {"pmcid": "PMC1", "pmid": "9"}, [1.0, 0.0]),
            FigureRecord("textbook", "2", ["collaterals"], "Collateral grading",
                         "", b"\x89PNG\r\n", {"heading_path": "Stroke>Fig1"}, [0.0, 1.0])]


def test_marks_term_with_embedded_image_and_source(tmp_path):
    img = tmp_path / "a.jpg"; img.write_bytes(b"JPEGBYTES")
    md = "## Imaging\n\nASPECTS guides EVT decisions.\n"
    html = render_briefing_html(md, _store(img),
                                embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" in html
    assert "ASPECTS" in html
    assert "data:image" in html
    assert "data:image/jpeg;base64," in html
    assert base64.b64encode(b"JPEGBYTES").decode() in html
    assert "PMC1" in html
    assert 'src="' + str(img) not in html


def test_unmatched_text_stays_plain(tmp_path):
    img = tmp_path / "a.jpg"; img.write_bytes(b"x")
    md = "## Plan\n\nNothing salient here.\n"
    html = render_briefing_html(md, _store(img), embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" not in html


def test_no_store_renders_plain_html(tmp_path):
    html = render_briefing_html("## H\n\nASPECTS.\n", [], embed_fn=None)
    assert "fig-card" not in html and "<h2" in html.lower()


def test_textbook_blob_png_mime(tmp_path):
    recs = [FigureRecord("textbook", "2", ["aspects"], "cap", "", b"\x89PNG\r\n\x1a\n",
                         {"heading_path": "H"}, [1.0, 0.0])]
    md = "## I\n\nASPECTS here.\n"
    html = render_briefing_html(md, recs, embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "data:image/png;base64," in html


def test_table_row_term_is_not_wrapped():
    # 'aspects' appears only inside a markdown table row -> must NOT be wrapped
    md = "## T\n\n| Indicator | Source |\n|---|---|\n| ASPECTS | x |\n"
    recs = [FigureRecord("image_bank", "1", ["aspects"], "cap", "", b"PNG",
                         {"pmcid": "PMC1"}, [1.0, 0.0])]
    html = render_briefing_html(md, recs, embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" not in html
