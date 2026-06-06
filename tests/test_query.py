# tests/test_query.py
from engine.query import Engine, QueryResult, Figure
from engine.index import Hit
from engine.synthesize import Synthesis, Citation


class FakeConfig:
    retrieve_k = 5
    rerank_k = 2
    max_figure_images = 3


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0, 1.0]


class FakeIndex:
    def __init__(self, hits):
        self.hits = hits
        self.called_with = None

    def hybrid_search(self, query_text, query_vector, k):
        self.called_with = (query_text, query_vector, k)
        return self.hits


class FakeReranker:
    def rerank(self, query, hits, top_k):
        return hits[:top_k]


class FakeSynthClient:
    def __init__(self):
        self.captured = {}

    def generate(self, system, user, images):
        self.captured = {"images": images}
        return "answer"


def capturing_synth(question, hits, figures, images, synth_client):
    synth_client.generate("sys", "user", images)
    return Synthesis(answer=f"ans:{len(hits)}:figs{len(figures)}",
                     citations=[Citation(1, "B", "C", 1)])


def test_engine_query_text_only():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]
    index = FakeIndex(hits)
    sc = FakeSynthClient()
    engine = Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                    synth_client=sc, synth_fn=capturing_synth)
    result = engine.query("normal icp?")
    assert isinstance(result, QueryResult)
    assert result.answer == "ans:2:figs0"
    assert index.called_with == ("normal icp?", [0.0, 1.0], 5)
    assert result.figures == []
    assert sc.captured["images"] == []


def test_engine_query_collects_figures(tmp_path):
    png = tmp_path / "p0012.png"
    png.write_bytes(b"PNGBYTES")
    hits = [
        Hit(id="a", book="Rhoton", chapter="Sellar", page=12, text="cs anatomy",
            has_figure=True, caption="Figure 12-1: cs", figure_path=str(png)),
        Hit(id="b", book="Greenberg", chapter="Tumors", page=40, text="text only"),
    ]
    sc = FakeSynthClient()
    engine = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                    synth_client=sc, synth_fn=capturing_synth)
    result = engine.query("cavernous sinus?")
    assert len(result.figures) == 1
    fig = result.figures[0]
    assert isinstance(fig, Figure)
    assert fig.source_n == 1
    assert fig.book == "Rhoton"
    assert fig.page == 12
    assert fig.image_path == str(png)
    assert sc.captured["images"] == [b"PNGBYTES"]  # bytes read from disk


def test_engine_query_respects_max_figure_images(tmp_path):
    png = tmp_path / "p1.png"
    png.write_bytes(b"X")
    hits = [Hit(id=str(i), book="Rhoton", chapter="C", page=i, text="t",
                has_figure=True, caption="cap", figure_path=str(png))
            for i in range(1, 4)]

    class Cfg(FakeConfig):
        rerank_k = 5
        max_figure_images = 2

    sc = FakeSynthClient()
    engine = Engine(Cfg(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                    synth_client=sc, synth_fn=capturing_synth)
    result = engine.query("q")
    # same figure_path dedupes to one figure regardless of the cap
    assert len(result.figures) == 1
