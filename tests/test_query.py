# tests/test_query.py
from engine.query import Engine, QueryResult, Figure
from engine.index import Hit
from engine.synthesize import Synthesis, Citation


class FakeConfig:
    retrieve_k = 5
    rerank_k = 3
    max_figure_images = 3
    visual_retrieval = True
    visual_retrieve_k = 5


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


class FakeVisualEmbedder:
    def embed_query(self, text):
        return [1.0, 0.0]


class FakeVisualIndex:
    def __init__(self, hits):
        self.hits = hits

    def image_search(self, query_vector, k):
        return self.hits


def capturing_synth(question, hits, figures, images, synth_client):
    synth_client.generate("sys", "user", images)
    return Synthesis(answer=f"ans:{len(hits)}:figs{len(figures)}",
                     citations=[Citation(1, "B", "C", 1)])


def _engine(cfg, index, synth, vemb=None, vidx=None):
    return Engine(cfg, FakeEmbedder(), index, FakeReranker(), synth_client=synth,
                  synth_fn=capturing_synth, visual_embedder=vemb, visual_index=vidx)


def test_engine_query_text_only():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]
    index = FakeIndex(hits)
    sc = FakeSynthClient()
    result = _engine(FakeConfig(), index, sc).query("normal icp?")
    assert isinstance(result, QueryResult)
    assert result.answer == "ans:2:figs0"
    assert index.called_with == ("normal icp?", [0.0, 1.0], 5)
    assert result.figures == []
    assert sc.captured["images"] == []


def test_engine_query_collects_text_figure(tmp_path):
    png = tmp_path / "p0012.png"
    png.write_bytes(b"PNGBYTES")
    hits = [
        Hit(id="a", book="Rhoton", chapter="Sellar", page=12, text="cs anatomy",
            has_figure=True, caption="Figure 12-1: cs", figure_path=str(png)),
        Hit(id="b", book="Greenberg", chapter="Tumors", page=40, text="text only"),
    ]
    sc = FakeSynthClient()
    result = _engine(FakeConfig(), FakeIndex(hits), sc).query("cavernous sinus?")
    assert len(result.figures) == 1
    fig = result.figures[0]
    assert isinstance(fig, Figure)
    assert fig.source_n == 1
    assert fig.book == "Rhoton"
    assert fig.image_path == str(png)
    assert sc.captured["images"] == [b"PNGBYTES"]


def test_visual_lane_appends_atlas_figure(tmp_path):
    png = tmp_path / "rhoton_p531.png"
    png.write_bytes(b"ATLAS")
    top = [Hit(id="a", book="Greenberg", chapter="T", page=40, text="t1"),
           Hit(id="b", book="NeuroICU", chapter="P", page=10, text="t2")]
    visual = [Hit(id="v", book="Rhoton", chapter="Sellar", page=531,
                  text="cs", has_figure=True, caption="cavernous sinus",
                  figure_path=str(png))]
    sc = FakeSynthClient()
    eng = _engine(FakeConfig(), FakeIndex(top), sc,
                  vemb=FakeVisualEmbedder(), vidx=FakeVisualIndex(visual))
    result = eng.query("cavernous sinus plate?")
    assert len(result.figures) == 1
    fig = result.figures[0]
    assert fig.book == "Rhoton"
    assert fig.page == 531
    assert fig.source_n == 3  # appended after the 2 passages (len(top)+1)
    assert sc.captured["images"] == [b"ATLAS"]


def test_visual_lane_disabled_when_off(tmp_path):
    png = tmp_path / "rhoton_p531.png"
    png.write_bytes(b"ATLAS")
    top = [Hit(id="a", book="Greenberg", chapter="T", page=40, text="t1")]
    visual = [Hit(id="v", book="Rhoton", chapter="S", page=531, text="cs",
                  has_figure=True, caption="cs", figure_path=str(png))]

    class Off(FakeConfig):
        visual_retrieval = False

    sc = FakeSynthClient()
    eng = _engine(Off(), FakeIndex(top), sc,
                  vemb=FakeVisualEmbedder(), vidx=FakeVisualIndex(visual))
    result = eng.query("q")
    assert result.figures == []


def test_respects_cap_distinct_paths(tmp_path):
    hits = []
    for i in range(1, 4):
        png = tmp_path / f"p{i}.png"
        png.write_bytes(b"X")
        hits.append(Hit(id=str(i), book="Rhoton", chapter="C", page=i, text="t",
                        has_figure=True, caption="cap", figure_path=str(png)))

    class Cfg(FakeConfig):
        rerank_k = 5
        max_figure_images = 2

    sc = FakeSynthClient()
    result = _engine(Cfg(), FakeIndex(hits), sc).query("q")
    assert len(result.figures) == 2
    assert len(sc.captured["images"]) == 2


def test_drops_missing_figure_file(tmp_path):
    missing = tmp_path / "gone.png"
    hits = [Hit(id="a", book="Rhoton", chapter="C", page=12, text="cs",
                has_figure=True, caption="cap", figure_path=str(missing)),
            Hit(id="b", book="Greenberg", chapter="C", page=40, text="text only")]
    sc = FakeSynthClient()
    result = _engine(FakeConfig(), FakeIndex(hits), sc).query("q")
    assert result.figures == []
    assert sc.captured["images"] == []


def test_select_figures_no_synthesis(tmp_path):
    png = tmp_path / "p12.png"
    png.write_bytes(b"PNG")
    hits = [Hit(id="a", book="Rhoton", chapter="S", page=12, text="cs",
                has_figure=True, caption="cap", figure_path=str(png))]
    sc = FakeSynthClient()
    eng = _engine(FakeConfig(), FakeIndex(hits), sc)
    figs = eng.select_figures("q")
    assert len(figs) == 1 and figs[0].book == "Rhoton"
    assert sc.captured == {}
