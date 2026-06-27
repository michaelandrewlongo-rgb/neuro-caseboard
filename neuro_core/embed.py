import numpy as np

from .config import resolve_device

# BGE-large asymmetric retrieval: queries get this prefix, documents get none.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Qwen3-Embedding uses an *instruction* on queries only (documents get none). Domain-specific task
# string (the official notes report 1-5% gains from a domain-specific instruct over the generic one).
_QWEN_TASK = "Given a neurosurgery question, retrieve relevant textbook passages that answer the question"
QWEN_QUERY_PROMPT = f"Instruct: {_QWEN_TASK}\nQuery:"


class Embedder:
    def __init__(self, model_name, device="cpu", encoder=None):
        self.model_name = model_name
        self.device = device
        self._encoder = encoder
        self._is_qwen = "Qwen3-Embedding" in model_name

    @property
    def encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            kwargs = {}
            if self._is_qwen:
                # Qwen3-Embedding does last-token pooling -> left-pad so the real last token is read.
                kwargs["tokenizer_kwargs"] = {"padding_side": "left"}
            self._encoder = SentenceTransformer(
                self.model_name, device=resolve_device(self.device), **kwargs)
        return self._encoder

    def embed_texts(self, texts):
        # Documents: no instruction prefix (both BGE and Qwen3).
        vecs = self.encoder.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")

    def embed_query(self, text):
        if self._is_qwen:
            # SentenceTransformer prepends `prompt` to the text (no separator), yielding
            # "Instruct: {task}\nQuery:{text}" — the official Qwen3-Embedding query format.
            vecs = self.encoder.encode([text], prompt=QWEN_QUERY_PROMPT, normalize_embeddings=True)
        else:
            vecs = self.encoder.encode([QUERY_PREFIX + text], normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")[0]
