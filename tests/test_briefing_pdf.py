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


def test_build_briefing_html_has_signal_tokens_and_content():
    doc = build_briefing_html(_Result(), title="My Briefing Title", subtitle="a subtitle")
    # content
    assert "My Briefing Title" in doc and "a subtitle" in doc
    assert "Indications" in doc and "Sources" in doc
    assert "[1]" in doc and "Greenberg, Trauma, p.1102" in doc
    assert "<strong>refractory</strong>" in doc        # markdown bold -> html
    # Signal design tokens
    assert "Syne" in doc                                # display font
    assert "#22d3ee" in doc and "#67e8f9" in doc        # teal signal
    assert "#ef4444" in doc                             # red signal accent
    assert 'class="dot"' in doc                         # red eyebrow signal dot


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
