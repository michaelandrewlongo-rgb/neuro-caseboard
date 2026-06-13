"""The FTS5 query sanitizer that keeps caseprep's CorpusRetriever from choking on
question punctuation/operators."""

from neuro_caseboard.retrieve import _SanitizingCorpus


def test_strips_fts_operators_and_punctuation():
    raw = "Confirm vertebral artery course (margin >= 5 mm, drill -> medial)?"
    cleaned = _SanitizingCorpus._clean(raw, 6)
    for bad in ("?", "(", ")", ">=", "->", ","):
        assert bad not in cleaned
    assert "vertebral" in cleaned and "artery" in cleaned


def test_drops_stopwords_and_caps_terms():
    cleaned = _SanitizingCorpus._clean(
        "Confirm the vertebral artery course and the corpectomy trough width", 4)
    terms = cleaned.split()
    assert len(terms) <= 4
    assert "the" not in terms and "and" not in terms


def test_empty_query_returns_empty():
    assert _SanitizingCorpus._clean("?? // (,)", 6) == ""


# --- textbook lexical lane (engine.index.Index.text_search) -----------------

from neuro_caseboard.retrieve import (
    _hit_to_dict, _index_search_fn, InProcessTextbookRetriever,
)


class _FakeHit:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_hit_to_dict_shape_and_defers_figures():
    h = _FakeHit(book="Greenberg", chapter="Tumors", page=792, text="acoustic neuroma...",
                 score=1.2, figure_path="fig/x.png", caption="Fig 1")
    d = _hit_to_dict(h)
    assert d["book"] == "Greenberg" and d["page"] == 792
    assert d["printed_page"] is None            # index stores PDF page only
    assert "figure_path" not in d               # figures deferred to a later visual lane
    assert d["text"].startswith("acoustic")


def test_index_search_fn_none_when_index_absent():
    assert _index_search_fn(index_dir="/no/such/index", repo="/no/such/repo") is None


def test_inprocess_retriever_maps_hits_to_cited_records():
    def fake_search(query, k):
        return [{"book": "Greenberg", "chapter": "Tumors", "page": 792,
                 "printed_page": None, "score": 1.0, "text": "facial nerve over tumor"}]
    recs = InProcessTextbookRetriever(fake_search).retrieve(
        "vestibular schwannoma facial nerve", top_n=3)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.source == "textbook"
    assert rec.metadata["citation"] == "Greenberg, p.792"
    assert rec.metadata["retrieval_source"] == "textbook_rag_inproc"


def test_inprocess_retriever_skips_hits_without_book_or_page():
    def fake_search(query, k):
        return [{"book": "", "page": 5, "text": "x"},             # no book -> skip
                {"book": "Schmidek", "page": None, "text": "y"},  # no page -> skip
                {"book": "Rhoton", "page": 10, "text": "z"}]      # kept
    recs = InProcessTextbookRetriever(fake_search).retrieve("q", top_n=5)
    assert [r.metadata["book"] for r in recs] == ["Rhoton"]
