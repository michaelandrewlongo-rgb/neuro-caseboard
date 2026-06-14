"""Standalone query path for the board-review `cards` lane.

Mirrors neuro_core.query: a process-scoped singleton (`get_cards_engine`) that
reuses the SAME Embedder and Reranker as the textbook engine, but searches the
`cards` table and returns the matched cards directly (no LLM synthesis — a
question bank surfaces real cards, it doesn't invent prose).

Install: copy this file to  neuro_core/cards_query.py
"""

from dataclasses import dataclass, field
from typing import List

from .config import load_config
from .embed import Embedder
from .rerank import Reranker
from .cards_index import CardsIndex, CardHit


@dataclass
class CardResult:
    query: str
    cards: List[CardHit] = field(default_factory=list)


class CardsEngine:
    def __init__(self, config, embedder, cards_index, reranker=None):
        self.config = config
        self.embedder = embedder
        self.cards_index = cards_index
        self.reranker = reranker

    def query(self, question, k=None, rerank=True):
        k = k or self.config.retrieve_k
        qv = self.embedder.embed_query(question)
        hits = self.cards_index.hybrid_search(question, qv, k)
        if rerank and self.reranker is not None and hits:
            # Reranker scores on hit.text; our cards carry the "Q: ... A: ..." text,
            # so the cross-encoder sees the full card — same contract as chunks.
            hits = self.reranker.rerank(question, hits, self.config.rerank_k)
        return CardResult(query=question, cards=hits)


_cards_engine = None


def get_cards_engine(config=None, with_reranker=True):
    global _cards_engine
    if _cards_engine is not None:
        return _cards_engine
    config = config or load_config()
    embedder = Embedder(config.embed_model, device=config.embed_device)
    cards_index = CardsIndex(config.index_dir)
    reranker = None
    if with_reranker:
        try:
            reranker = Reranker(config.rerank_model, device=config.embed_device)
        except Exception:
            reranker = None
    _cards_engine = CardsEngine(config, embedder, cards_index, reranker)
    return _cards_engine


def cards_query(question, config=None, k=None, rerank=True):
    return get_cards_engine(config).query(question, k=k, rerank=rerank)
