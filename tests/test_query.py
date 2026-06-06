# tests/test_query.py
from engine.query import Engine, QueryResult
from engine.index import Hit
from engine.synthesize import Synthesis, Citation


class FakeConfig:
    retrieve_k = 5
    rerank_k = 2
    openrouter_model = "m"


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0, 1.0]


class FakeIndex:
    def __init__(self):
        self.called_with = None

    def hybrid_search(self, query_text, query_vector, k):
        self.called_with = (query_text, query_vector, k)
        return [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
                Hit(id="b", book="B", chapter="C", page=2, text="t2")]


class FakeReranker:
    def rerank(self, query, hits, top_k):
        return hits[:top_k]


def fake_synth(question, hits, client, model):
    return Synthesis(answer=f"ans:{len(hits)}",
                     citations=[Citation(1, "B", "C", 1)])


def test_engine_query_orchestration():
    index = FakeIndex()
    engine = Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                    client=None, synth_fn=fake_synth)
    result = engine.query("normal icp?")

    assert isinstance(result, QueryResult)
    assert result.answer == "ans:2"
    assert index.called_with == ("normal icp?", [0.0, 1.0], 5)
    assert len(result.citations) == 1
