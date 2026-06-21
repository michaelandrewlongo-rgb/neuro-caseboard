from types import SimpleNamespace

from neuro_caseboard.briefing_pdf import build_briefing_html


def _lit():
    cite = SimpleNamespace(n=1, pmid="111", title="Tenecteplase before EVT",
                           journal="Stroke", year=2024, doi="10.1161/abc",
                           url="https://pubmed.ncbi.nlm.nih.gov/111/")
    return SimpleNamespace(narrative="Recent RCTs expand EVT to distal vessels [L1].",
                           citations=[cite])


def _result(literature=None):
    return SimpleNamespace(answer="Answer [1].",
                           citations=[SimpleNamespace(n=1, book="Bk", chapter="", page=3)],
                           figures=[], literature=literature)


def test_literature_section_rendered_when_present():
    html = build_briefing_html(_result(_lit()), title="Q")
    assert "Contemporary Literature" in html
    assert "[L1]" in html
    assert "Tenecteplase before EVT" in html
    assert "https://doi.org/10.1161/abc" in html  # DOI link preferred


def test_no_literature_section_when_absent():
    html = build_briefing_html(_result(None), title="Q")
    assert "Contemporary Literature" not in html


def test_literature_html_renders_refs_without_narrative():
    from neuro_caseboard.briefing_pdf import _literature_html
    result = SimpleNamespace(literature=SimpleNamespace(
        narrative="",
        citations=[SimpleNamespace(n=1, title="DISTAL trial", journal="NEJM",
                                   year=2024, doi="10/x", url="u")]))
    html = _literature_html(result)
    assert "Contemporary Literature" in html
    assert "[L1]" in html and "DISTAL trial" in html


def test_literature_html_empty_when_no_citations():
    from neuro_caseboard.briefing_pdf import _literature_html
    result = SimpleNamespace(literature=SimpleNamespace(narrative="", citations=[]))
    assert _literature_html(result) == ""
