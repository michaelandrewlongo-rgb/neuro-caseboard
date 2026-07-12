"""Phase 3.1: the folio (printed_page) is carried into the Citation and shown to the reader,
so a citation points at a page a human can actually open. FIX_PLAN §4.1 (3.1)."""
from neuro_core.index import Hit
from neuro_core.synthesize import Citation, build_citations, _format_passages


def _hit(printed_page):
    return Hit(id="Youmans::p5710::0", book="Youmans", chapter="Chapter 419", page=5710,
               text="Intracranial occlusive disease…", printed_page=printed_page)


def test_citation_carries_folio_from_hit():
    cits = build_citations([_hit("3357")], figures=[])
    assert cits[0].printed_page == "3357"


def test_page_ref_prefers_folio():
    assert Citation(1, "Youmans", "Chapter 419", 5710, printed_page="3357").page_ref == "p.3357"


def test_page_ref_marks_pdf_fallback_when_no_folio():
    # Pure-scan books (no folio text layer) must not present the PDF page as a book page.
    assert Citation(1, "Bridwell", "", 400, printed_page="").page_ref == "p.400 (pdf)"


def test_format_passages_shows_folio_to_llm():
    # The LLM must see the folio so it cites the openable page, not the PDF index.
    passages = _format_passages([_hit("3357")])
    assert "p.3357" in passages and "p.5710" not in passages
