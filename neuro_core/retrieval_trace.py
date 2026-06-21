"""Grader-independent retrieval instrumentation.

Captures the ranked candidate sets at BOTH crowd-out gates the council identified:

  * the **recall** gate  - the fused (RRF) top-``RETRIEVE_K`` pool, before rerank;
  * the **selection** gate - the FULL cross-encoder ordering (every candidate the
    reranker scored), with a ``selected`` flag for those inside top-``RERANK_K``.

Recording the *full* selection ordering (not just the surviving top-k) is what makes
displacement analysis possible WITHOUT reindexing a no-Youmans corpus: removing one
``book``'s chunks from the ordering and re-taking the top-k is an exact counterfactual
for "what would the answer context have been without that book" (``displacement``).

This module is pure data + arithmetic; it never calls a grader or an LLM. It exists to
settle, mechanistically, whether adding a book *evicts* otherwise-selected passages
(real crowd-out) vs. merely correlating with regression-to-the-mean in the scores.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class TracedCandidate:
    id: str
    book: str
    page: int
    score: float
    rank: int
    selected: bool = False


@dataclass
class RetrievalTrace:
    """One query's retrieval, at both gates. Populated by ``index.hybrid_search``
    (recall) and ``rerank.Reranker.rerank`` (selection) when passed as ``trace=``."""

    question: str
    qid: str | None = None
    retrieve_k: int = 0
    rerank_k: int = 0
    recall: list = field(default_factory=list)      # list[TracedCandidate], fused pre-rerank
    selection: list = field(default_factory=list)   # list[TracedCandidate], FULL reranked order

    def record_recall(self, hits) -> None:
        """``hits``: the fused top-k Hit list from ``hybrid_search`` (``hit.score`` is RRF)."""
        self.recall = [
            TracedCandidate(h.id, h.book, int(h.page), float(h.score), i)
            for i, h in enumerate(hits)
        ]

    def record_selection(self, ranked_pairs, top_k: int) -> None:
        """``ranked_pairs``: the FULL ``[(hit, score), ...]`` list sorted best-first
        (every reranked candidate, not the top-k slice). ``top_k``: the cut size."""
        self.rerank_k = top_k
        self.selection = [
            TracedCandidate(h.id, h.book, int(h.page), float(s), i, selected=i < top_k)
            for i, (h, s) in enumerate(ranked_pairs)
        ]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "qid": self.qid,
            "retrieve_k": self.retrieve_k,
            "rerank_k": self.rerank_k,
            "recall": [asdict(c) for c in self.recall],
            "selection": [asdict(c) for c in self.selection],
        }


def _matches_book(candidate: TracedCandidate, book_lower: str) -> bool:
    return book_lower in (candidate.book or "").lower()


def displacement(trace: RetrievalTrace, book: str, *, lane: str = "selection",
                 top_k: int | None = None) -> dict:
    """Counterfactual crowd-out for one query: if ``book``'s chunks were removed from
    the ranked pool, which other passages would rise into the top-k that are currently
    pushed below the cut?

    ``lane="selection"`` (default) analyses the cross-encoder ordering at ``RERANK_K``
    (the answer-affecting gate). ``lane="recall"`` analyses the RRF pool at ``RETRIEVE_K``
    (catches eviction that happens *before* the reranker ever sees a passage).

    Returns:
      ``intruders``  - ``book`` candidates occupying the actual top-k.
      ``displaced``  - non-``book`` candidates that would be in the top-k WITHOUT ``book``
                       but are not in the actual top-k (i.e. evicted by ``book``).
      ``n_displaced``, plus score summaries so a marginal eviction (a weak ``book`` chunk
      barely outscoring a strong incumbent) is distinguishable from a deserved one.
    """
    ordering = trace.selection if lane == "selection" else trace.recall
    if top_k is None:
        top_k = trace.rerank_k if lane == "selection" else trace.retrieve_k
    book_lower = book.strip().lower()

    actual_topk = ordering[:top_k]
    actual_ids = {c.id for c in actual_topk}
    without_book = [c for c in ordering if not _matches_book(c, book_lower)][:top_k]

    intruders = [c for c in actual_topk if _matches_book(c, book_lower)]
    displaced = [c for c in without_book if c.id not in actual_ids]

    return {
        "qid": trace.qid,
        "lane": lane,
        "top_k": top_k,
        "intruders": intruders,
        "displaced": displaced,
        "n_intruders": len(intruders),
        "n_displaced": len(displaced),
        "intruder_scores": [c.score for c in intruders],
        "displaced_scores": [c.score for c in displaced],
        # The diagnostic the council wanted: is the lowest-ranked book chunk that took a
        # slot barely above the strongest passage it evicted? Small gap => marginal,
        # RTM-style churn; large gap => the book genuinely dominated.
        "min_intruder_score": min((c.score for c in intruders), default=None),
        "max_displaced_score": max((c.score for c in displaced), default=None),
    }


def aggregate_displacement(traces, book: str, *, lane: str = "selection",
                           top_k: int | None = None) -> dict:
    """Roll up per-query ``displacement`` across a benchmark run into the evidence the
    council asked for: does adding ``book`` actually evict passages, and is the eviction
    *marginal* (a weak book chunk barely beating a strong incumbent - the artifact-adjacent
    case) or *decisive* (book clearly dominated)?

    ``marginal_gap`` per question = ``min_intruder_score - max_displaced_score`` (always
    >= 0, since the global ordering is by score). SMALL gaps => contestable eviction;
    LARGE gaps => the book deserved the slot. A pile-up of near-zero gaps is the signature
    of crowd-out that hurts (strong incumbents lost to barely-better book chunks)."""
    rows = [displacement(t, book, lane=lane, top_k=top_k) for t in traces]
    n_q = len(rows)
    gaps = [r["min_intruder_score"] - r["max_displaced_score"] for r in rows
            if r["min_intruder_score"] is not None and r["max_displaced_score"] is not None]
    total_displaced = sum(r["n_displaced"] for r in rows)
    return {
        "book": book,
        "lane": lane,
        "n_questions": n_q,
        "questions_with_intruder": sum(1 for r in rows if r["n_intruders"] > 0),
        "questions_with_displacement": sum(1 for r in rows if r["n_displaced"] > 0),
        "total_displaced": total_displaced,
        "mean_displaced_per_q": (total_displaced / n_q) if n_q else 0.0,
        "marginal_gaps": gaps,
        "mean_marginal_gap": (sum(gaps) / len(gaps)) if gaps else None,
        "rows": rows,
    }
