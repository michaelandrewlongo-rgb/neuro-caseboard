from neuro_core.evidence import (
    EvidenceRef, from_citation, from_figure, from_figure_item, record, other_features,
)


class _C:
    def __init__(self, n, book, chapter, page):
        self.n, self.book, self.chapter, self.page = n, book, chapter, page


class _F:
    def __init__(self, source_n, book, chapter, page, image_path, caption):
        self.source_n, self.book, self.chapter = source_n, book, chapter
        self.page, self.image_path, self.caption = page, image_path, caption


class _FI:
    def __init__(self, fig_id, image_path, caption, citation):
        self.fig_id, self.image_path = fig_id, image_path
        self.caption, self.citation = caption, citation


def test_key_figure_vs_citation():
    assert EvidenceRef(figure_path="/x/p1.png").key == "fig:/x/p1.png"
    assert EvidenceRef(book="Rhoton", page=538).key == "cite:Rhoton|538"


def test_from_citation_maps_fields_and_key():
    r = from_citation(_C(1, "Greenberg", "Tumors", 792))
    assert r.book == "Greenberg" and r.page == 792 and r.chapter == "Tumors"
    assert r.citation == "Greenberg, p.792" and r.figure_path is None
    assert r.key == "cite:Greenberg|792" and r.source == "qa"


def test_from_figure_sets_figure_path_key():
    r = from_figure(_F(2, "Rhoton", "CPA", 538, "/x/p538.png", "AICA in the CPA"))
    assert r.figure_path == "/x/p538.png" and r.caption == "AICA in the CPA"
    assert r.citation == "Rhoton, p.538" and r.key == "fig:/x/p538.png"


def test_from_figure_item_keys_on_path_without_book_page():
    r = from_figure_item(_FI("F1", "/x/p538.png", "AICA in the CPA", "Rhoton, p.538"))
    assert r.figure_path == "/x/p538.png" and r.citation == "Rhoton, p.538"
    assert r.key == "fig:/x/p538.png" and r.source == "board"


def test_record_and_other_features_cross_link():
    store = {}
    record(store, [from_figure(_F(1, "Rhoton", "CPA", 538, "/x/p538.png", "cap"))], 'answer: "q"')
    record(store, [from_figure_item(_FI("F1", "/x/p538.png", "cap", "Rhoton, p.538"))], 'board: "t"')
    assert other_features(store, "fig:/x/p538.png", 'answer: "q"') == ['board: "t"']
    assert other_features(store, "fig:/x/p538.png", 'board: "t"') == ['answer: "q"']


def test_other_features_excludes_same_label_only():
    store = {}
    record(store, [from_figure(_F(1, "Rhoton", "", 540, "/x/p540.png", "c"))], 'answer: "q"')
    assert other_features(store, "fig:/x/p540.png", 'answer: "q"') == []
