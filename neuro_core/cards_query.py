"""Standalone query path for the board-review `cards` lane.

Mirrors neuro_core.query: a process-scoped singleton (`get_cards_engine`) that
searches the `cards` table and returns the matched cards directly (no LLM
synthesis — a question bank surfaces real cards, it doesn't invent prose).

To honor the "zero new infrastructure" intent, the engine reuses the textbook
engine's already-loaded Embedder/Reranker when that engine exists in-process
(e.g. the Streamlit app uses both lanes); otherwise it loads its own, so the
standalone `caseboard cards` path doesn't build the full textbook engine.
"""

import re
from dataclasses import dataclass, field
from typing import List

from .config import load_config
from .embed import Embedder
from .rerank import Reranker
from .cards_index import CardsIndex, CardHit


class CardsIndexNotBuilt(RuntimeError):
    """Raised when the `cards` table hasn't been built yet."""


# The deck's own low-confidence self-labels. Surfaces should flag these rather
# than present such a card as authoritative (see flagged_tags()).
LOW_CONFIDENCE_TAGS = {
    "questionable", "to-verify", "toverify", "to_verify", "unverified",
    "verify", "wrong", "needs-verification", "needsverification", "unsure",
}


def flagged_tags(tags):
    """Return the deck's own low-confidence tag tokens present in `tags`
    (e.g. 'questionable', 'to-verify'), so callers can warn instead of
    presenting the card as verified."""
    toks = re.split(r"[\s,;]+", (tags or "").lower())
    return [t for t in toks if t in LOW_CONFIDENCE_TAGS]


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
        # `k` is the DISPLAY count the caller wants (CLI -k / Streamlit slider).
        # Retrieve a wide candidate pool like the textbook engine, then let the
        # reranker (or a plain top-k cut) decide how many cards come back.
        k = k or self.config.rerank_k
        qv = self.embedder.embed_query(question)
        hits = self.cards_index.hybrid_search(question, qv, self.config.retrieve_k)
        if rerank and self.reranker is not None and hits:
            # Reranker scores on hit.text; our cards carry the "Q: ... A: ..." text,
            # so the cross-encoder sees the full card — same contract as chunks.
            hits = self.reranker.rerank(question, hits, k)
        else:
            hits = hits[:k]
        return CardResult(query=question, cards=hits)


_cards_engine = None


def _shared_models(config, with_reranker):
    """Reuse the textbook engine's loaded models if it's already built in this
    process; otherwise load our own. Avoids a second BGE-large + cross-encoder
    load when both lanes run in one process (the Streamlit app)."""
    try:
        from . import query as _q
        existing = _q._engine
    except Exception:
        existing = None
    if existing is not None:
        return existing.embedder, (existing.reranker if with_reranker else None)
    embedder = Embedder(config.embed_model, device=config.embed_device)
    reranker = None
    if with_reranker:
        try:
            reranker = Reranker(config.rerank_model, device=config.embed_device)
        except Exception:
            reranker = None
    return embedder, reranker


def get_cards_engine(config=None, with_reranker=True):
    global _cards_engine
    if _cards_engine is not None:
        return _cards_engine
    config = config or load_config()
    try:
        cards_index = CardsIndex(config.index_dir)
    except Exception as e:
        raise CardsIndexNotBuilt(
            "The board-review `cards` table isn't built yet. Build it with:\n"
            "    python -m neuro_core.scripts.build_cards_index"
        ) from e
    embedder, reranker = _shared_models(config, with_reranker)
    _cards_engine = CardsEngine(config, embedder, cards_index, reranker)
    return _cards_engine


def cards_query(question, config=None, k=None, rerank=True):
    return get_cards_engine(config).query(question, k=k, rerank=rerank)
