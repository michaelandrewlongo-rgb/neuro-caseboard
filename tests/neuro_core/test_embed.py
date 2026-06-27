# tests/test_embed.py
import numpy as np
from neuro_core.embed import Embedder, QUERY_PREFIX


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


class FakeEncoderWithPrompt:
    """Mimics SentenceTransformer.encode(..., prompt=...) for the Qwen3-Embedding path."""
    def __init__(self):
        self.seen = []

    def encode(self, texts, prompt=None, normalize_embeddings=False):
        self.seen.append((list(texts), prompt, normalize_embeddings))
        return np.array([[float(len(t)), 1.0] for t in texts])


def test_embed_query_qwen_uses_instruct_prompt_not_bge_prefix():
    from neuro_core.embed import QWEN_QUERY_PROMPT
    enc = FakeEncoderWithPrompt()
    emb = Embedder("Qwen/Qwen3-Embedding-0.6B", encoder=enc)
    emb.embed_query("aneurysm clipping")
    assert enc.seen[0][0] == ["aneurysm clipping"]   # raw query text, NO BGE prefix
    assert enc.seen[0][1] == QWEN_QUERY_PROMPT        # Instruct prompt passed via prompt=
    assert QWEN_QUERY_PROMPT.startswith("Instruct:")


def test_embed_texts_qwen_has_no_prompt():
    enc = FakeEncoderWithPrompt()
    emb = Embedder("Qwen/Qwen3-Embedding-0.6B", encoder=enc)
    emb.embed_texts(["doc text"])
    assert enc.seen[0][0] == ["doc text"]
    assert enc.seen[0][1] is None                     # documents: no instruction
