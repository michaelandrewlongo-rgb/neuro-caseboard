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
