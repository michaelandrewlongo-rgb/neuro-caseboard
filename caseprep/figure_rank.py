"""Pick the single most relevant figure for a term's context. Pure-Python cosine
over unit-norm embeddings; deterministic tag-overlap fallback when no embedder
(returns None when overlap is zero)."""
from __future__ import annotations

import re
from typing import Callable

from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def best_figure(context: str, candidates: list[FigureRecord], *,
                embed_fn: EmbedFn | None, floor: float = 0.35) -> FigureRecord | None:
    if not candidates:
        return None
    if embed_fn is not None:
        q = embed_fn([context])[0]
        scored = [(_dot(q, c.embedding) if c.embedding else -1.0, c) for c in candidates]
        scored.sort(key=lambda sc: (-sc[0], f"{sc[1].source}:{sc[1].fig_id}"))
        top_score, top = scored[0]
        return top if top_score >= floor else None
    ctx = _tokens(context)
    def overlap(c: FigureRecord) -> int:
        return len(ctx & _tokens(" ".join(c.tags)))
    ranked = sorted(candidates, key=lambda c: (-overlap(c), f"{c.source}:{c.fig_id}"))
    return ranked[0] if overlap(ranked[0]) > 0 else None
