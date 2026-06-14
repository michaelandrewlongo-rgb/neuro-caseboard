from .config import resolve_device


class Reranker:
    def __init__(self, model_name, device="cpu", scorer=None):
        self.model_name = model_name
        self.device = device
        self._scorer = scorer

    @property
    def scorer(self):
        if self._scorer is None:
            from sentence_transformers import CrossEncoder
            self._scorer = CrossEncoder(
                self.model_name, device=resolve_device(self.device))
        return self._scorer

    def rerank(self, query, hits, top_k):
        if not hits:
            return []
        pairs = [(query, h.text) for h in hits]
        scores = self.scorer.predict(pairs)
        ranked = sorted(zip(hits, scores), key=lambda hs: float(hs[1]), reverse=True)
        out = []
        for hit, score in ranked[:top_k]:
            hit.score = float(score)
            out.append(hit)
        return out
