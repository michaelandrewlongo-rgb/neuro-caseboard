import fitz
import pytest


@pytest.fixture
def tiny_pdf(tmp_path):
    """A 4-page PDF named 'Sample Book.pdf' with a 2-chapter TOC."""
    path = tmp_path / "Sample Book.pdf"
    doc = fitz.open()
    bodies = [
        "Introduction alpha: clinical content about diagnosis and patient management",
        "Introduction beta: imaging content about radiographic evaluation and findings",
        "Methods gamma: operative content about surgical technique and exposure steps",
        "Methods delta: content about postoperative care and complication management",
    ]
    for i, body in enumerate(bodies):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} {body}")
    doc.set_toc([[1, "Introduction", 1], [1, "Methods", 3]])
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def pdf_with_figure(tmp_path):
    """2-page PDF 'Atlas Book.pdf': page 1 has a large image + a caption line;
    page 2 is text-only."""
    path = tmp_path / "Atlas Book.pdf"
    doc = fitz.open()
    p1 = doc.new_page()  # default A4 595x842 pts
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 400))
    pix.clear_with(200)  # fill gray so it's a real raster image
    p1.insert_image(fitz.Rect(50, 50, 550, 550), pixmap=pix)  # ~0.5 of page area
    p1.insert_text((50, 700), "Figure 1-1: Lateral view of the cavernous sinus")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Page 2 plain clinical text without imagery")
    doc.save(path)
    doc.close()
    return path
