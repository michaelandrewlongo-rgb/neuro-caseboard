# tests/test_rerank.py
from neuro_core.rerank import Reranker
from neuro_core.index import Hit


class FakeScorer:
    """Scores by presence of 'good' in the passage text."""
    def predict(self, pairs):
        return [10.0 if "good" in text else 0.0 for _q, text in pairs]


def _hit(id_, text):
    return Hit(id=id_, book="B", chapter="C", page=1, text=text)


def test_rerank_orders_and_truncates():
    hits = [_hit("1", "bad"), _hit("2", "good match"), _hit("3", "bad")]
    out = Reranker("fake", scorer=FakeScorer()).rerank("q", hits, top_k=2)
    assert len(out) == 2
    assert out[0].id == "2"
    assert out[0].score == 10.0


def test_rerank_empty():
    assert Reranker("fake", scorer=FakeScorer()).rerank("q", [], top_k=3) == []
