import numpy as np

from .config import resolve_device

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, model_name, device="cpu", encoder=None):
        self.model_name = model_name
        self.device = device
        self._encoder = encoder

    @property
    def encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(
                self.model_name, device=resolve_device(self.device))
        return self._encoder

    def embed_texts(self, texts):
        vecs = self.encoder.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")

    def embed_query(self, text):
        vecs = self.encoder.encode([QUERY_PREFIX + text], normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")[0]
