from .config import resolve_device
from .select import mmr_select


class Reranker:
    def __init__(self, model_name, device="cpu", scorer=None,
                 mmr_book_penalty=0.0, mmr_page_penalty=0.0):
        self.model_name = model_name
        self.device = device
        self._scorer = scorer
        # Phase 1-D diversity penalties (0 => plain top-k, behavior unchanged).
        self.mmr_book_penalty = mmr_book_penalty
        self.mmr_page_penalty = mmr_page_penalty

    @property
    def scorer(self):
        if self._scorer is None:
            from sentence_transformers import CrossEncoder
            self._scorer = CrossEncoder(
                self.model_name, device=resolve_device(self.device))
        return self._scorer

    def rerank(self, query, hits, top_k, trace=None):
        if not hits:
            return []
        pairs = [(query, h.text) for h in hits]
        scores = self.scorer.predict(pairs)
        ranked = sorted(zip(hits, scores), key=lambda hs: float(hs[1]), reverse=True)
        chosen = mmr_select(ranked, top_k, book_penalty=self.mmr_book_penalty,
                            page_penalty=self.mmr_page_penalty)
        if trace is not None:                 # record FULL ordering + what actually survived
            trace.record_selection(ranked, top_k,
                                   selected_ids={h.id for h, _ in chosen})
        out = []
        for hit, score in chosen:
            hit.score = float(score)
            out.append(hit)
        return out
