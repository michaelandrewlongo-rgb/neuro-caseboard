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


def test_verify_banner_on_every_page(rendered):
    # WS-5: the standing confidentiality/verify banner appears on every page.
    _, out, _ = rendered
    doc = fitz.open(out)
    assert doc.page_count >= 1
    for page in doc:
        assert "verifies every recommendation" in page.get_text()


def test_section_literature_renders_L_axis_in_pdf(tmp_path):
    # WS-5/WS-3: a section's contemporary-literature block renders with [L#] in the fpdf2 PDF.
    from types import SimpleNamespace
    from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim
    lit = SimpleNamespace(
        narrative="Recent RCTs support decompression [L1].",
        citations=[SimpleNamespace(n=1, title="ACDF RCT", journal="Spine", year=2024,
                                   doi="10.1/abc", url="")])
    d = Dossier(title="Case Dossier — C5-6 ACDF", summary=EvidenceSummary(to_verify=1),
                sections=[Section(heading="Clinical Reasoning",
                                  claims=[Claim(text="Indicated", why="progressive")],
                                  literature=lit)])
    out = tmp_path / "case.pdf"
    render_pdf(d, out)
    text = "\n".join(page.get_text() for page in fitz.open(out))
    assert "Contemporary Literature" in text
    assert "[L1]" in text and "ACDF RCT" in text
