"""Unit tests for diversity-aware selection (Phase 1-D, neuro_core/select.py)."""
from neuro_core.index import Hit
from neuro_core.select import mmr_select


def _h(id_, book, page=1):
    return Hit(id=id_, book=book, chapter="C", page=page, text="t")


def _scored(*triples):
    # triples: (id, book, score) sorted best-first by score
    return [(_h(i, b, p), s) for (i, b, p, s) in triples]


def test_zero_penalty_is_plain_topk():
    scored = _scored(("a", "Youmans", 1, 9.0), ("b", "Youmans", 2, 8.0),
                     ("c", "Rhoton", 3, 7.0))
    out = mmr_select(scored, k=2, book_penalty=0.0)
    assert [h.id for h, _ in out] == ["a", "b"]          # identical to ranked[:k]


def test_book_penalty_breaks_near_tie_toward_diversity():
    # b (Youmans, 8.0) and c (Rhoton, 7.9) are near-tied; after picking a (Youmans),
    # a soft same-book penalty flips the 2nd slot to the other book.
    scored = _scored(("a", "Youmans", 1, 9.0), ("b", "Youmans", 2, 8.0),
                     ("c", "Rhoton", 3, 7.9))
    out = mmr_select(scored, k=2, book_penalty=0.2)
    assert [h.id for h, _ in out] == ["a", "c"]          # Rhoton promoted over 2nd Youmans
    assert [round(s, 1) for _h, s in out] == [9.0, 7.9]  # raw scores preserved


def test_decisive_win_survives_penalty():
    # The 2nd Youmans chunk is decisively better (8.9) than the only alternative (2.0);
    # a soft penalty must NOT flip it — diversity should only break genuine near-ties.
    scored = _scored(("a", "Youmans", 1, 9.0), ("b", "Youmans", 2, 8.9),
                     ("c", "Rhoton", 3, 2.0))
    out = mmr_select(scored, k=2, book_penalty=0.2)
    assert [h.id for h, _ in out] == ["a", "b"]


def test_page_penalty_suppresses_same_page_duplicates():
    # Two chunks from the SAME Youmans page vs a different Youmans page; page_penalty
    # should prefer spreading across pages even within one book.
    scored = _scored(("a", "Youmans", 10, 9.0), ("b", "Youmans", 10, 8.5),
                     ("c", "Youmans", 20, 8.4))
    out = mmr_select(scored, k=2, book_penalty=0.0, page_penalty=0.3)
    assert [h.id for h, _ in out] == ["a", "c"]          # different page beats same-page dup


def test_empty_and_short_inputs():
    assert mmr_select([], k=3, book_penalty=0.2) == []
    one = _scored(("a", "Youmans", 1, 9.0))
    assert [h.id for h, _ in mmr_select(one, k=5, book_penalty=0.2)] == ["a"]
