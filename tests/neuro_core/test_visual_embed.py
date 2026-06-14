import numpy as np

from neuro_core.visual_embed import VisualEmbedder, _l2_normalize


class FakeBackend:
    """Returns fixed RAW (un-normalized) vectors so we can test normalization."""
    def encode_images(self, paths):
        return np.array([[3.0, 4.0]] * len(paths), dtype="float32")

    def encode_text(self, text):
        return np.array([0.0, 2.0], dtype="float32")


def test_l2_normalize_unit_rows():
    out = _l2_normalize(np.array([[3.0, 4.0], [0.0, 0.0]], dtype="float32"))
    assert np.allclose(np.linalg.norm(out, axis=1), [1.0, 0.0])  # zero row stays zero


def test_embed_images_normalized_shape():
    emb = VisualEmbedder("dummy-model", backend=FakeBackend())
    vecs = emb.embed_images(["a.png", "b.png"])
    assert vecs.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vecs, axis=1), [1.0, 1.0])
    assert np.allclose(vecs[0], [0.6, 0.8])


def test_embed_images_empty_returns_empty():
    emb = VisualEmbedder("dummy-model", backend=FakeBackend())
    out = emb.embed_images([])
    assert out.shape[0] == 0


def test_embed_query_is_unit_vector_1d():
    emb = VisualEmbedder("dummy-model", backend=FakeBackend())
    v = emb.embed_query("cavernous sinus")
    assert v.shape == (2,)
    assert np.allclose(v, [0.0, 1.0])
