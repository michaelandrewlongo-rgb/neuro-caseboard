# tests/test_index.py
import numpy as np
import pytest
from neuro_core.index import reciprocal_rank_fusion, build_index, Index
from neuro_core.chunk import Chunk


def test_rrf_rewards_agreement():
    # 'b' is rank-0 in BOTH rankings -> unambiguously highest fused score
    fused = reciprocal_rank_fusion([["b", "a", "c"], ["b", "c", "a"]])
    ids = [i for i, _ in fused]
    assert ids[0] == "b"
    assert set(ids) == {"a", "b", "c"}


class FakeEmbedder:
    """Deterministic 2-D vectors so vector search is predictable."""
    def __init__(self):
        self.table = {
            "icp": [1.0, 0.0],
            "spine": [0.0, 1.0],
        }

    def embed_texts(self, texts):
        out = []
        for t in texts:
            out.append([1.0, 0.0] if "icp" in t.lower() else [0.0, 1.0])
        return np.array(out, dtype="float32")

    def embed_query(self, text):
        return np.array(self.table["icp" if "icp" in text.lower() else "spine"],
                        dtype="float32")


@pytest.mark.integration
def test_build_and_hybrid_search(tmp_path):
    chunks = [
        Chunk(id="x::p1::0", book="NeuroICU", chapter="Pressure",
              page=10, text="normal icp range is 5 to 15 mmHg"),
        Chunk(id="y::p2::0", book="Benzel", chapter="Fusion",
              page=20, text="spine pedicle screw fixation technique"),
    ]
    emb = FakeEmbedder()
    build_index(chunks, emb, tmp_path / "idx")
    idx = Index(tmp_path / "idx")

    hits = idx.hybrid_search("what is normal icp", emb.embed_query("icp"), k=2)
    assert hits[0].book == "NeuroICU"
    assert hits[0].page == 10
    assert hits[0].chapter == "Pressure"


@pytest.mark.integration
def test_figure_columns_round_trip(tmp_path):
    chunks = [
        Chunk(id="a::p1::0", book="Rhoton", chapter="Sellar", page=12,
              text="cavernous sinus anatomy lateral view", has_figure=True,
              caption="Figure 12-1: cavernous sinus", figure_path="/x/p0012.png"),
        Chunk(id="b::p2::0", book="Greenberg", chapter="Tumors", page=40,
              text="meningioma grading text only"),
    ]
    emb = FakeEmbedder()
    build_index(chunks, emb, tmp_path / "idx")
    idx = Index(tmp_path / "idx")
    hits = idx.hybrid_search("cavernous sinus", emb.embed_query("spine"), k=2)
    by_book = {h.book: h for h in hits}
    assert by_book["Rhoton"].has_figure is True
    assert by_book["Rhoton"].figure_path == "/x/p0012.png"
    assert "cavernous sinus" in by_book["Rhoton"].caption
    assert by_book["Greenberg"].has_figure is False
    assert by_book["Greenberg"].figure_path is None
