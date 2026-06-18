"""Real text embedder (all-mpnet-base-v2, 768-d, unit-norm). Build-time only;
lazily imports sentence-transformers so the package import stays light."""
from __future__ import annotations

_MODEL = None
MODEL_NAME = "all-mpnet-base-v2"


def embed_texts(texts: list[str]) -> list[list[float]]:
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL_NAME)
    vecs = _MODEL.encode(texts, normalize_embeddings=True, batch_size=64)
    return [list(map(float, v)) for v in vecs]
