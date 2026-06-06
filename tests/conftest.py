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
