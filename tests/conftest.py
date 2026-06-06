import fitz
import pytest


@pytest.fixture
def tiny_pdf(tmp_path):
    """A 4-page PDF named 'Sample Book.pdf' with a 2-chapter TOC."""
    path = tmp_path / "Sample Book.pdf"
    doc = fitz.open()
    bodies = [
        "Introduction alpha content about diagnosis",
        "Introduction beta content about imaging",
        "Methods gamma content about surgical technique",
        "Methods delta content about postoperative care",
    ]
    for i, body in enumerate(bodies):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} {body}")
    doc.set_toc([[1, "Introduction", 1], [1, "Methods", 3]])
    doc.save(path)
    doc.close()
    return path
