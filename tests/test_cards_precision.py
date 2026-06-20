"""Hermetic tests for Cards retrieval precision (neuro_core/cards_precision.py), BACKLOG P4 #12.

Pure post-filter logic — no embedder/index/network."""
from neuro_core.cards_index import CardHit
from neuro_core.cards_precision import (RefinedCards, refine, spinal_levels,
                                        level_ok, exact_overlap, query_terms)


def _hit(qt="", at="", score=0.0):
    return CardHit(id=qt[:8] or "x", question_text=qt, answer_text=at, score=score)


def test_spinal_levels_parses_ranges_and_singles():
    assert spinal_levels("C5-6 ACDF") == {"c5", "c6"}
    assert spinal_levels("T12-L1 fracture") == {"t12", "l1"}
    assert spinal_levels("C5-C6 disc") == {"c5", "c6"}
    assert spinal_levels("no level here") == set()


def test_level_ok_drops_adjacent_mismatch_keeps_exact_and_unlevelled():
    q = spinal_levels("C5-6 ACDF")
    assert level_ok(q, _hit("C5-6 anterior cervical discectomy")) is True   # exact
    assert level_ok(q, _hit("C6-7 ACDF technique")) is False                # adjacent mismatch
    assert level_ok(q, _hit("general ACDF positioning")) is True            # no level -> kept


def test_exact_overlap_counts_shared_terms():
    qt = query_terms("cavernous sinus contents")
    assert exact_overlap(qt, _hit("contents of the cavernous sinus")) >= 2


def test_refine_drops_mismatched_level_and_caps_k():
    hits = [
        _hit("C5-6 ACDF approach", score=0.40),
        _hit("C6-7 ACDF approach", score=0.90),   # higher score but WRONG level -> dropped
        _hit("C5-6 complication", score=0.30),
    ]
    out = refine(hits, "C5-6 ACDF", k=5)
    ids_levels = [spinal_levels(h.question_text) for h in out.cards]
    assert {"c6", "c7"} not in ids_levels          # the adjacent-level card is gone
    assert len(out.cards) == 2


def test_refine_exact_term_boost_reorders_on_weak_scores():
    # Near-tied base scores: the card literally containing the query terms should rank first.
    hits = [
        _hit("unrelated adjacent anatomy", score=0.21),
        _hit("borders of the cavernous sinus", score=0.20),
    ]
    out = refine(hits, "cavernous sinus borders", k=5)
    assert "cavernous sinus" in out.cards[0].question_text


def test_refine_relevance_threshold_suppresses_weak_when_enabled():
    hits = [_hit("strong match cavernous sinus", score=1.0),
            _hit("weak tangential mention", score=0.1)]
    out = refine(hits, "cavernous sinus", k=5, keep_ratio=0.5)
    assert len(out.cards) == 1                      # the weak one is suppressed


def test_refine_empty_yields_note():
    out = refine([], "anything", k=5)
    assert isinstance(out, RefinedCards) and out.cards == [] and out.note


def test_cards_engine_applies_precision_filter():
    """End-to-end: the engine drops an anatomically-mismatched card. Hermetic fakes."""
    from neuro_core.cards_query import CardsEngine

    class _Cfg:
        retrieve_k = 10
        rerank_k = 5

    class _Emb:
        def embed_query(self, q):
            return [0.0]

    class _Idx:
        def hybrid_search(self, q, qv, k):
            return [_hit("C5-6 ACDF approach", score=0.4),
                    _hit("C6-7 ACDF approach", score=0.9),   # higher score, WRONG level
                    _hit("general ACDF positioning", score=0.2)]

    eng = CardsEngine(_Cfg(), _Emb(), _Idx(), reranker=None)
    res = eng.query("C5-6 ACDF", k=5)
    texts = [c.question_text for c in res.cards]
    assert "C6-7 ACDF approach" not in texts    # mismatched level dropped by the engine
    assert any("C5-6" in t for t in texts)
