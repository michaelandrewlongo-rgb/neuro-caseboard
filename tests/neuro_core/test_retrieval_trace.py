"""Unit tests for grader-independent retrieval instrumentation (Phase 0A)."""
import pytest

from neuro_core.index import Hit
from neuro_core.rerank import Reranker
from neuro_core.retrieval_trace import (
    RetrievalTrace, aggregate_displacement, displacement)


def _hit(id_, book, page, text, score=0.0):
    return Hit(id=id_, book=book, chapter="C", page=page, text=text, score=score)


class _BookScorer:
    """Cross-encoder stub: score is encoded in the passage text as 'score=<float>'."""
    def predict(self, pairs):
        return [float(text.split("score=")[1]) for _q, text in pairs]


def test_record_recall_captures_rank_and_score():
    trace = RetrievalTrace(question="q")
    trace.record_recall([_hit("a", "B1", 1, "x", 0.9), _hit("b", "B2", 2, "y", 0.4)])
    assert [c.id for c in trace.recall] == ["a", "b"]
    assert [c.rank for c in trace.recall] == [0, 1]
    assert trace.recall[0].score == 0.9


def test_record_selection_flags_topk():
    trace = RetrievalTrace(question="q")
    pairs = [(_hit("a", "B", 1, "t"), 5.0), (_hit("b", "B", 2, "t"), 3.0),
             (_hit("c", "B", 3, "t"), 1.0)]
    trace.record_selection(pairs, top_k=2)
    assert [c.selected for c in trace.selection] == [True, True, False]
    assert trace.rerank_k == 2


def test_rerank_populates_full_selection_not_just_topk():
    # The reranker keeps top_k=2 but the trace must hold ALL scored candidates.
    hits = [_hit("a", "Youmans", 1, "score=1.0"), _hit("b", "Greenberg", 2, "score=9.0"),
            _hit("c", "Youmans", 3, "score=8.0"), _hit("d", "Rhoton", 4, "score=7.0")]
    trace = RetrievalTrace(question="q")
    out = Reranker("fake", scorer=_BookScorer()).rerank("q", hits, top_k=2, trace=trace)
    assert [h.id for h in out] == ["b", "c"]            # returned slice unchanged
    assert len(trace.selection) == 4                    # full ordering captured
    assert [c.id for c in trace.selection] == ["b", "c", "d", "a"]
    assert [c.selected for c in trace.selection] == [True, True, False, False]


def test_rerank_without_trace_is_unchanged():
    hits = [_hit("a", "B", 1, "score=1.0"), _hit("b", "B", 2, "score=9.0")]
    out = Reranker("fake", scorer=_BookScorer()).rerank("q", hits, top_k=1)
    assert [h.id for h in out] == ["b"]


def test_displacement_identifies_evicted_passage():
    # Reranked order: Youmans(9) , Greenberg(8) , Youmans(7) , Rhoton(6). top_k=2.
    # Actual top-2 = {Y9, G8}. Without Youmans top-2 = {G8, R6}. So Rhoton(6) is
    # displaced by a Youmans chunk; the surviving Youmans intruder scored 9.
    trace = RetrievalTrace(question="q", qid="TEST-1")
    pairs = [(_hit("y1", "Youmans", 1, "t"), 9.0), (_hit("g1", "Greenberg", 2, "t"), 8.0),
             (_hit("y2", "Youmans", 3, "t"), 7.0), (_hit("r1", "Rhoton", 4, "t"), 6.0)]
    trace.record_selection(pairs, top_k=2)
    d = displacement(trace, "youmans")
    assert d["n_displaced"] == 1
    assert d["displaced"][0].id == "r1"
    assert [c.id for c in d["intruders"]] == ["y1"]
    assert d["min_intruder_score"] == 9.0
    assert d["max_displaced_score"] == 6.0


def test_displacement_none_when_book_absent():
    trace = RetrievalTrace(question="q")
    pairs = [(_hit("g1", "Greenberg", 1, "t"), 9.0), (_hit("r1", "Rhoton", 2, "t"), 8.0)]
    trace.record_selection(pairs, top_k=1)
    d = displacement(trace, "youmans")
    assert d["n_displaced"] == 0 and d["n_intruders"] == 0


def test_displacement_recall_lane():
    trace = RetrievalTrace(question="q")
    trace.record_recall([_hit("y1", "Youmans", 1, "t", 0.9), _hit("g1", "Greenberg", 2, "t", 0.5),
                         _hit("r1", "Rhoton", 3, "t", 0.3)])
    trace.retrieve_k = 3
    d = displacement(trace, "youmans", lane="recall", top_k=2)
    assert d["lane"] == "recall"
    assert d["displaced"][0].id == "r1"      # Youmans@top-2 pushes Rhoton out of the pool


def _trace_with_selection(qid, pairs, top_k):
    t = RetrievalTrace(question="q", qid=qid)
    t.record_selection(pairs, top_k)
    return t


def test_aggregate_marginal_vs_decisive_gap():
    # Q1: a weak Youmans chunk (score 8.1) evicts a strong Rhoton (8.0) -> marginal gap 0.1.
    q1 = _trace_with_selection("Q1", [
        (_hit("y1", "Youmans", 1, "t"), 9.0), (_hit("y2", "Youmans", 2, "t"), 8.1),
        (_hit("r1", "Rhoton", 3, "t"), 8.0)], top_k=2)
    # Q2: Youmans (9.0) clearly beats the strongest non-book passage (Greenberg 5.0)
    # -> decisive gap 4.0 (the displaced passage is the top non-book one, not the weakest).
    q2 = _trace_with_selection("Q2", [
        (_hit("y3", "Youmans", 1, "t"), 9.0), (_hit("g1", "Greenberg", 2, "t"), 5.0),
        (_hit("g2", "Greenberg", 3, "t"), 2.0)], top_k=1)
    agg = aggregate_displacement([q1, q2], "youmans")
    assert agg["n_questions"] == 2
    assert agg["questions_with_displacement"] == 2
    assert agg["total_displaced"] == 2
    assert agg["marginal_gaps"] == pytest.approx([0.1, 4.0])
    assert agg["mean_marginal_gap"] == pytest.approx(2.05)


def test_to_dict_round_trips():
    trace = RetrievalTrace(question="q", qid="X-1")
    trace.record_recall([_hit("a", "B", 1, "t", 0.5)])
    trace.record_selection([(_hit("a", "B", 1, "t"), 5.0)], top_k=1)
    d = trace.to_dict()
    assert d["qid"] == "X-1"
    assert d["recall"][0]["id"] == "a"
    assert d["selection"][0]["selected"] is True
