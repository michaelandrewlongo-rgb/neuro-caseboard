"""The Q&A figure lane must pass the question as the region signal and use the STRICT guard
subset (cranial<->spine + non-op-angio), so off-domain plates stop leaking into answers while
angiographic figures survive. Boards keep the full guard set; this only covers the Q&A path."""
from neuro_core.query import Engine


class _Cfg:
    caption_retrieval = True
    caption_retrieve_k = 8


class _FakeCapIdx:
    def __init__(self):
        self.kw = None

    def retrieve(self, query, *, topic="", top_n=8, guard_set="full"):
        self.kw = dict(query=query, topic=topic, top_n=top_n, guard_set=guard_set)
        return []


def test_caption_hits_passes_question_as_topic_and_strict_guards():
    idx = _FakeCapIdx()
    eng = Engine(_Cfg(), None, None, None, None, caption_index=idx)
    q = "structures at risk clipping an MCA bifurcation aneurysm"
    eng._caption_hits(q)
    assert idx.kw["query"] == q
    assert idx.kw["topic"] == q              # question doubles as the region signal
    assert idx.kw["guard_set"] == "strict"   # not the full board set
    assert idx.kw["top_n"] == 8
