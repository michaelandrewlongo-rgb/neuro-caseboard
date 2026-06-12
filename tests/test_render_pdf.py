"""PDF renderer: produces a valid artifact whose extracted text shows the fixes,
with real Unicode glyphs (defect #1: no '?'/box replacement)."""

import fitz  # pymupdf
import pytest
from PIL import Image

from caseprep.core.contracts import ArtifactRef
from neuro_caseboard.compile import compile_dossier
from neuro_caseboard.render_pdf import render_pdf
import tests.fixtures as fx


def _real_png(path):
    Image.new("RGB", (420, 300), "white").save(path)


@pytest.fixture(params=fx.ALL_TOPICS)
def rendered(request, tmp_path):
    f = fx.build(request.param)
    d = compile_dossier(f.manifest, topic=f.topic, evidence=f.evidence,
                        card_evidence=f.card_evidence, page_texts=f.page_texts)
    # point the figure at a real PNG so pdf.image() has something to embed
    png = tmp_path / "fig.png"
    _real_png(png)
    for s in d.sections:
        for fig in s.figures:
            fig.image_path = str(png)
    out = tmp_path / "case-board.pdf"
    art = render_pdf(d, out)
    text = "\n".join(page.get_text() for page in fitz.open(out))
    return art, out, text


def test_returns_pdf_artifact(rendered):
    art, out, _ = rendered
    assert isinstance(art, ArtifactRef)
    assert art.kind == "pdf"
    assert out.stat().st_size > 1000


def test_unicode_markers_render_not_question_marks(rendered):
    # #1: the embedded font renders the glyphs themselves, extractable as real chars
    _, _, text = rendered
    assert "✓" in text
    assert "⚠" in text
    assert "�" not in text  # no replacement character


def test_no_confidence_noise_in_pdf(rendered):
    _, _, text = rendered
    assert "[low]" not in text
    assert "high / medium / low" not in text.lower()


def test_legend_and_crosslink_in_pdf(rendered):
    _, _, text = rendered
    assert "corpus-supported" in text
    assert "Fig F1" in text


def test_appendix_in_pdf(rendered):
    _, _, text = rendered
    assert "Appendix" in text
