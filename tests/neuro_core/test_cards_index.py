"""Offline test for the cards lane, mirroring tests/neuro_core/test_index.py.

Install: copy to  tests/neuro_core/test_cards_index.py
Run:     pytest tests/neuro_core/test_cards_index.py -m integration
"""
import numpy as np
import pytest

from neuro_core.cards_index import build_cards_index, CardsIndex


class FakeEmbedder:
    """Deterministic 2-D vectors so vector search is predictable."""
    def embed_texts(self, texts):
        out = [[1.0, 0.0] if "icp" in t.lower() else [0.0, 1.0] for t in texts]
        return np.array(out, dtype="float32")

    def embed_query(self, text):
        return np.array([1.0, 0.0] if "icp" in text.lower() else [0.0, 1.0],
                        dtype="float32")


def _cards():
    return [
        {"id": "c1", "question_text": "What is normal ICP?",
         "answer_text": "5 to 15 mmHg", "deck_name": "SANS",
         "tags": "physiology", "image_paths": ["/m/icp.png"],
         "text": "Q: What is normal ICP?\nA: 5 to 15 mmHg"},
        {"id": "c2", "question_text": "Pedicle screw entry point?",
         "answer_text": "spine fixation landmark", "deck_name": "SANS",
         "tags": "spine", "image_paths": [],
         "text": "Q: Pedicle screw entry point?\nA: spine fixation landmark"},
    ]


@pytest.mark.integration
def test_build_and_hybrid_search(tmp_path):
    emb = FakeEmbedder()
    build_cards_index(_cards(), emb, tmp_path / "idx")
    idx = CardsIndex(tmp_path / "idx")

    hits = idx.hybrid_search("what is normal icp", emb.embed_query("icp"), k=2)
    assert hits[0].id == "c1"
    assert hits[0].deck_name == "SANS"
    assert hits[0].image_paths == ["/m/icp.png"]
    assert "5 to 15" in hits[0].answer_text


@pytest.mark.integration
def test_text_lane_finds_keyword(tmp_path):
    emb = FakeEmbedder()
    build_cards_index(_cards(), emb, tmp_path / "idx")
    idx = CardsIndex(tmp_path / "idx")
    hits = idx.text_search("pedicle screw", k=2)
    assert hits and hits[0].id == "c2"


class RecordingReranker:
    """Records the top_k it was asked for; returns the top_k hits unchanged."""
    def __init__(self):
        self.last_top_k = None

    def rerank(self, query, hits, top_k):
        self.last_top_k = top_k
        return list(hits)[:top_k]


@pytest.mark.integration
def test_engine_k_is_display_count_not_rerank_k(tmp_path):
    # Regression: the user's k (CLI -k / Streamlit slider) must drive how many
    # cards return — it was previously capped at config.rerank_k.
    from types import SimpleNamespace
    from neuro_core.cards_query import CardsEngine
    emb = FakeEmbedder()
    build_cards_index(_cards(), emb, tmp_path / "idx")
    idx = CardsIndex(tmp_path / "idx")
    cfg = SimpleNamespace(retrieve_k=20, rerank_k=6)
    rr = RecordingReranker()
    eng = CardsEngine(cfg, emb, idx, rr)

    res = eng.query("what is normal icp", k=1)
    assert rr.last_top_k == 1            # explicit k wins
    assert len(res.cards) == 1
    eng.query("what is normal icp")      # default k -> rerank_k (not retrieve_k)
    assert rr.last_top_k == cfg.rerank_k


@pytest.mark.integration
def test_engine_without_reranker_caps_at_k(tmp_path):
    from types import SimpleNamespace
    from neuro_core.cards_query import CardsEngine
    emb = FakeEmbedder()
    build_cards_index(_cards(), emb, tmp_path / "idx")
    idx = CardsIndex(tmp_path / "idx")
    cfg = SimpleNamespace(retrieve_k=20, rerank_k=6)
    eng = CardsEngine(cfg, emb, idx, reranker=None)
    assert len(eng.query("icp", k=1).cards) == 1


def test_flagged_tags_detects_low_confidence_labels():
    from neuro_core.cards_query import flagged_tags
    assert flagged_tags("spine questionable") == ["questionable"]
    assert flagged_tags("anatomy, to-verify") == ["to-verify"]
    assert flagged_tags("physiology high-yield") == []
    assert flagged_tags("") == []
