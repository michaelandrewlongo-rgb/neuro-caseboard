# tests/test_embed.py
import numpy as np
from engine.embed import Embedder, QUERY_PREFIX


class FakeEncoder:
    def __init__(self):
        self.seen = []

    def encode(self, texts, normalize_embeddings=False):
        self.seen.append((list(texts), normalize_embeddings))
        return np.array([[float(len(t)), 1.0] for t in texts])


def test_embed_texts_shape_and_dtype():
    enc = FakeEncoder()
    emb = Embedder("fake", encoder=enc)
    vecs = emb.embed_texts(["aa", "bbbb"])
    assert vecs.shape == (2, 2)
    assert vecs.dtype == np.float32
    assert enc.seen[0][1] is True  # normalize_embeddings passed


def test_embed_query_applies_prefix():
    enc = FakeEncoder()
    emb = Embedder("fake", encoder=enc)
    vec = emb.embed_query("aneurysm clipping")
    assert vec.shape == (2,)
    assert enc.seen[0][0][0] == QUERY_PREFIX + "aneurysm clipping"
