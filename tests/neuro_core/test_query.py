# tests/test_query.py
import neuro_core.query as q
from neuro_core.query import Engine, QueryResult, Figure, Clarification
from neuro_core.query_analyze import VariantRewrite
from neuro_core.index import Hit
from neuro_core.synthesize import Synthesis, Citation


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


def test_rrf_dedups_multichunk_page(tmp_path):
    # A figure page split across 2 chunks must not get an inflated RRF score and
    # displace single-chunk pages. Reranked order: Y(0), Z(1), X(2), X(3).
    def fig(book, page, fname):
        p = tmp_path / fname
        p.write_bytes(b"X")
        return Hit(id=f"{book}{page}", book=book, chapter="C", page=page,
                   text="t", has_figure=True, caption="c", figure_path=str(p))

    y = fig("BookY", 1, "y.png")
    z = fig("BookZ", 2, "z.png")
    x1 = fig("BookX", 3, "x.png")
    x2 = Hit(id="x3b", book="BookX", chapter="C", page=3, text="t2",
             has_figure=True, caption="c", figure_path=x1.figure_path)
    top = [y, z, x1, x2]

    class Cfg(FakeConfig):
        rerank_k = 5
        max_figure_images = 2

    sc = FakeSynthClient()
    result = _engine(Cfg(), FakeIndex(top), sc).query("q")
    # Without dedup, X's doubled rank would beat Z and the set would be {X,Y}.
    assert {f.book for f in result.figures} == {"BookY", "BookZ"}


def test_visual_lane_error_falls_back(tmp_path):
    png = tmp_path / "p12.png"
    png.write_bytes(b"PNG")
    top = [Hit(id="a", book="Rhoton", chapter="S", page=12, text="cs",
               has_figure=True, caption="c", figure_path=str(png))]

    class BoomEmbedder:
        def embed_query(self, text):
            raise RuntimeError("model load failed")

    sc = FakeSynthClient()
    eng = _engine(FakeConfig(), FakeIndex(top), sc,
                  vemb=BoomEmbedder(), vidx=FakeVisualIndex([]))
    result = eng.query("q")  # must not raise
    assert len(result.figures) == 1
    assert result.figures[0].book == "Rhoton"  # text lane still works


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


def test_refusal_drops_figures_and_citations(tmp_path):
    # Real-shaped reproduction of the reported bug: retrieval yields a figure-bearing
    # hit (so figures ARE collected upstream), but synthesis abstains. A "Not found in
    # the provided sources." answer must carry NO figures and NO sources — both are
    # spurious retrieval artifacts when nothing relevant was found.
    png = tmp_path / "p0012.png"
    png.write_bytes(b"PNGBYTES")
    hits = [Hit(id="a", book="Rhoton", chapter="Sellar", page=12, text="cs",
                has_figure=True, caption="cap", figure_path=str(png))]

    def refusal_synth(question, hits, figures, images, synth_client):
        synth_client.generate("sys", "user", images)
        # figures/citations were collected, but the model found nothing.
        return Synthesis(answer="Not found in the provided sources.",
                         citations=[Citation(1, "Rhoton", "Sellar", 12)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=refusal_synth)
    result = eng.query("what's the weather today?")
    assert result.answer == "Not found in the provided sources."
    assert result.figures == []      # the bug: previously non-empty
    assert result.citations == []    # same root cause (sources are also spurious)


def test_normal_answer_keeps_figures_and_citations(tmp_path):
    # Guard against over-correction: a real (non-refusal) answer must STILL carry its
    # figures and citations. This is the tempting wrong-but-adjacent failure mode.
    png = tmp_path / "p0012.png"
    png.write_bytes(b"PNGBYTES")
    hits = [Hit(id="a", book="Rhoton", chapter="Sellar", page=12, text="cs",
                has_figure=True, caption="cap", figure_path=str(png))]

    def answer_synth(question, hits, figures, images, synth_client):
        synth_client.generate("sys", "user", images)
        return Synthesis(answer="The cavernous sinus contains CN III-VI [1].",
                         citations=[Citation(1, "Rhoton", "Sellar", 12)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=answer_synth)
    result = eng.query("cavernous sinus contents?")
    assert len(result.figures) == 1
    assert len(result.citations) == 1


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


def _stub_engine(_config):
    class _E:
        def query(self, question):
            return f"ANS:{question}"
    return _E()


def test_query_runs_guard_for_local_provider(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "local"
        gpu_guard = True

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("force", force))
    monkeypatch.setattr(q, "get_engine", _stub_engine)
    out = q.query("hi", config=Cfg(), force=True)
    assert out == "ANS:hi"
    assert calls["force"] is True  # force propagated to the guard


def test_query_skips_guard_for_non_local(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "vertex"
        gpu_guard = True

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("ran", True))
    monkeypatch.setattr(q, "get_engine", _stub_engine)
    q.query("hi", config=Cfg())
    assert "ran" not in calls


def test_query_skips_guard_when_disabled(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "local"
        gpu_guard = False

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("ran", True))
    monkeypatch.setattr(q, "get_engine", _stub_engine)
    q.query("hi", config=Cfg())
    assert "ran" not in calls


def test_answer_prepends_bold_assuming_line_when_variant_set():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]

    def synth(question, hits, figures, images, synth_client, variant_directive=None):
        synth_client.generate("s", "u", images)
        return Synthesis(answer="Body of the answer [1].",
                         citations=[Citation(1, "B", "C", 1)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=synth)
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "unilateral FTP rewrite")
    result = eng._answer("unilateral FTP rewrite", hits, variant=vr)
    assert result.answer.startswith(
        "**Assuming unilateral FTP hemicraniectomy (most consistent with retrieved sources).**")
    assert "Body of the answer [1]." in result.answer


def test_answer_refusal_gets_no_assuming_line():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]

    def refusal(question, hits, figures, images, synth_client, variant_directive=None):
        synth_client.generate("s", "u", images)
        return Synthesis(answer="Not found in the provided sources.",
                         citations=[Citation(1, "B", "C", 1)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=refusal)
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "x")
    result = eng._answer("x", hits, variant=vr)
    assert result.answer == "Not found in the provided sources."
    assert result.citations == []
    assert result.figures == []


def test_answer_non_variant_has_no_assuming_line():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]

    def synth(question, hits, figures, images, synth_client, variant_directive=None):
        synth_client.generate("s", "u", images)
        return Synthesis(answer="Plain body [1].", citations=[Citation(1, "B", "C", 1)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=synth)
    result = eng._answer("q", hits)  # no variant
    assert result.answer == "Plain body [1]."
    assert "**Assuming" not in result.answer
