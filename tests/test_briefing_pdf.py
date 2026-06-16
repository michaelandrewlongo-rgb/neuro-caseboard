"""The Signal briefing HTML builder is pure (no Playwright/Chromium needed) and must carry the
Neurosurgery Signal design tokens, the content, and robustly skip unreadable figures."""
from neuro_caseboard.briefing_pdf import build_briefing_html


class _C:
    def __init__(self, n, book, chapter, page):
        self.n, self.book, self.chapter, self.page = n, book, chapter, page


class _F:
    def __init__(self, source_n, book, page, image_path, caption):
        self.source_n, self.book, self.page = source_n, book, page
        self.image_path, self.caption = image_path, caption


class _Result:
    answer = "### Indications\nDecompressive craniectomy relieves **refractory** ICP [1]."
    citations = [_C(1, "Greenberg", "Trauma", 1102)]
    figures = [_F(7, "Schmidek and Sweet", 942, "/no/such/figure.png", "a figure")]


def test_build_briefing_html_has_exec_navy_tokens_and_content():
    doc = build_briefing_html(_Result(), title="My Briefing Title", subtitle="a subtitle")
    # content
    assert "My Briefing Title" in doc and "a subtitle" in doc
    assert "Indications" in doc and "Sources" in doc
    assert "[1]" in doc and "Greenberg, Trauma, p.1102" in doc
    assert "<strong>refractory</strong>" in doc          # markdown bold -> html
    # Executive-Navy design tokens (replaces the old Signal asserts)
    assert "Archivo" in doc and "Source+Serif+4" in doc and "IBM+Plex+Mono" in doc
    assert "#0e7490" in doc                              # deep-teal accent
    assert "NEURO·CASEBOARD" in doc                 # masthead brand
    assert "Ask · Citation-grounded" in doc         # eyebrow chip


def test_build_briefing_html_skips_unreadable_figure():
    # the only figure points at a bogus path -> dropped, no crash, no broken <figure>
    doc = build_briefing_html(_Result(), title="T")
    assert "<figure>" not in doc


def test_build_briefing_html_accepts_dict_shaped_result():
    result = {
        "answer": "Plain answer.",
        "citations": [{"n": 1, "book": "Rhoton", "chapter": "", "page": 538}],
        "figures": [],
    }
    doc = build_briefing_html(result, title="Dict Title")
    assert "Dict Title" in doc and "Rhoton, p.538" in doc


def test_assuming_line_renders_as_bold_strong():
    from neuro_caseboard.briefing_pdf import build_briefing_html
    from neuro_core.query import QueryResult

    answer = ("**Assuming unilateral FTP hemicraniectomy (most consistent with retrieved "
              "sources).**\n\nThe flap is 12x15 cm [1].")
    html = build_briefing_html(QueryResult(answer=answer), title="DHC")
    assert "<strong>Assuming unilateral FTP hemicraniectomy" in html
    assert "&gt; Assuming" not in html  # never a literal blockquote marker
