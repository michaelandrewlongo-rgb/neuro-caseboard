import neuro_core.query as q
from neuro_core.query import Engine, RetrievalBundle, Clarification
from neuro_core.query_analyze import VariantRewrite, Gate, QueryAnalysis
from neuro_core.index import Hit
from neuro_core.synthesize import Synthesis, Citation

# tests/neuro_core/ has no __init__.py so cross-module imports from
# tests.neuro_core.test_query fail at collection.  Fakes are defined
# locally here (verbatim copies from test_query.py).


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


def capturing_synth(question, hits, figures, images, synth_client, variant_directive=None):
    synth_client.generate("sys", "user", images)
    return Synthesis(answer=f"ans:{len(hits)}:figs{len(figures)}",
                     citations=[Citation(1, "B", "C", 1)])


def _engine(index, gate_fn=None, analyze_fn=None):
    return Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                  synth_client=FakeSynthClient(), synth_fn=capturing_synth,
                  gate_fn=gate_fn or (lambda question, hits: Gate(tripped=False)),
                  analyze_fn=analyze_fn or (lambda q, h, sc: QueryAnalysis(ambiguous=False)))


def test_retrieve_for_synthesis_returns_bundle_no_synth():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]
    sc = FakeSynthClient()
    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=sc, synth_fn=capturing_synth,
                 gate_fn=lambda question, h: Gate(tripped=False))
    bundle = eng.retrieve_for_synthesis("normal icp?")
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.question == "normal icp?"
    assert [h.page for h in bundle.hits] == [1, 2]
    assert bundle.figures == [] and bundle.images == []
    assert bundle.variant is None
    assert sc.captured == {}  # synthesis NOT called


def test_retrieve_for_synthesis_short_circuits_clarification():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    vr1 = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    vr2 = VariantRewrite("bifrontal (Kjellberg) decompression", "bifrontal rewrite")
    analyze = lambda qq, h, sc: QueryAnalysis(ambiguous=True, axis="x",
                                              variants=[vr1, vr2], chosen=vr1, confidence=0.2)
    eng = _engine(FakeIndex(hits), gate_fn=lambda question, h: Gate(tripped=True, axis="x"),
                  analyze_fn=analyze)
    out = eng.retrieve_for_synthesis("decompressive craniectomy steps?")
    assert isinstance(out, Clarification)


def test_retrieve_for_synthesis_carries_resolved_variant():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    analyze = lambda qq, h, sc: QueryAnalysis(
        ambiguous=True, axis="x",
        variants=[vr, VariantRewrite("bifrontal (Kjellberg) decompression", "b rewrite")],
        chosen=vr, confidence=0.9)
    index = FakeIndex(hits)
    eng = _engine(index, gate_fn=lambda question, h: Gate(tripped=True, axis="x"),
                  analyze_fn=analyze)
    bundle = eng.retrieve_for_synthesis("decompressive craniectomy steps?")
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.question == "uni rewrite"
    assert bundle.variant is vr
    assert index.called_with[0] == "uni rewrite"  # figures collected on the resolved query


def test_plan_retrieval_runs_guard_for_local(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "local"
        gpu_guard = True

    class _E:
        def retrieve_for_synthesis(self, question):
            return f"BUNDLE:{question}"

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("force", force))
    monkeypatch.setattr(q, "get_engine", lambda config: _E())
    out = q.plan_retrieval("hi", config=Cfg(), force=True)
    assert out == "BUNDLE:hi"
    assert calls["force"] is True
