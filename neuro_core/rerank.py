from .config import resolve_device


class Reranker:
    def __init__(self, model_name, device="cpu", scorer=None):
        self.model_name = model_name
        self.device = device
        self._scorer = scorer

    @property
    def scorer(self):
        if self._scorer is None:
            if "Qwen3-Reranker" in self.model_name:
                from .qwen3_reranker import Qwen3Reranker
                self._scorer = Qwen3Reranker(device=resolve_device(self.device))
            else:
                from sentence_transformers import CrossEncoder
                self._scorer = CrossEncoder(
                    self.model_name, device=resolve_device(self.device))
        return self._scorer

    def rerank(self, query, hits, top_k):
        if not hits:
            return []
        if self.model_name == "none":
            # RRF-only arm: keep the hybrid-search (RRF) fusion order; no cross-encoder rescoring.
            # (query.py applies the vascular off-domain sort + rerank_k slice afterwards, unchanged.)
            return list(hits)[:top_k]
        pairs = [(query, h.text) for h in hits]
        scores = self.scorer.predict(pairs)
        ranked = sorted(zip(hits, scores), key=lambda hs: float(hs[1]), reverse=True)
        out = []
        for hit, score in ranked[:top_k]:
            hit.score = float(score)
            out.append(hit)
        return out
