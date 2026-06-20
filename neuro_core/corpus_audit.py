"""Corpus gap audit (BACKLOG P1 #3): score high-yield topic coverage against the index and
emit a clinically-prioritized expansion worklist.

Pure core: every function operates on an injected ``probe: Callable[[str], Coverage]`` so the
logic is hermetically testable. The real probe over the engine lives in ``index_probe``; it is
the only part that touches the corpus."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    probe_query: str
    consequence: int  # 1..5 — clinical consequence of missing this topic
    frequency: int    # 1..5 — expected query frequency


@dataclass
class Coverage:
    top_score: float    # best reranked hit score for the probe query
    n_strong_hits: int  # number of hits judged strong by the probe


@dataclass
class GapRow:
    topic: Topic
    status: str           # "covered" | "weak" | "absent"
    coverage: Coverage
    priority: int         # consequence * frequency


def classify(cov: Coverage, *, strong_top: float, weak_top: float, min_strong: int = 2) -> str:
    """covered = a strong top hit AND enough strong hits; weak = some signal; absent = none."""
    if cov.top_score >= strong_top and cov.n_strong_hits >= min_strong:
        return "covered"
    if cov.top_score >= weak_top:
        return "weak"
    return "absent"


def audit(topics: Iterable[Topic], probe: Callable[[str], Coverage], *,
          strong_top: float, weak_top: float, min_strong: int = 2) -> list[GapRow]:
    rows = []
    for t in topics:
        cov = probe(t.probe_query)
        rows.append(GapRow(topic=t,
                           status=classify(cov, strong_top=strong_top, weak_top=weak_top,
                                           min_strong=min_strong),
                           coverage=cov,
                           priority=t.consequence * t.frequency))
    return rows


_STATUS_RANK = {"absent": 0, "weak": 1}  # absent sorts before weak on a priority tie


def prioritized_gaps(rows: Iterable[GapRow]) -> list[GapRow]:
    gaps = [r for r in rows if r.status in _STATUS_RANK]
    return sorted(gaps, key=lambda r: (-r.priority, _STATUS_RANK[r.status], r.topic.label))


def render_report(rows: Iterable[GapRow]) -> str:
    gaps = prioritized_gaps(rows)
    lines = ["# Corpus expansion worklist — high-yield gaps",
             "",
             "Ranked by clinical consequence x expected query frequency. "
             "Coverage probed against the current index.",
             "",
             "| Priority | Topic | Status | Consequence | Frequency | Top score | Strong hits |",
             "|---:|---|---|---:|---:|---:|---:|"]
    for r in gaps:
        lines.append(f"| {r.priority} | {r.topic.label} | {r.status} | "
                     f"{r.topic.consequence} | {r.topic.frequency} | "
                     f"{r.coverage.top_score:.3f} | {r.coverage.n_strong_hits} |")
    if not gaps:
        lines.append("| — | _no gaps detected_ | — | — | — | — | — |")
    return "\n".join(lines) + "\n"


def index_probe(engine=None, config=None, strong_ratio: float = 0.6):
    """Build a coverage probe over the engine's retrieval seam (read-only).

    A hit is "strong" relative to the query's own top score (RRF scores are not absolute):
    ``score >= strong_ratio * top_score``. Returns Coverage(0.0, 0) for a query with no hits."""
    if engine is None:
        from neuro_core.query import get_engine
        engine = get_engine(config)

    def _probe(query: str) -> Coverage:
        hits = engine._retrieve(query)
        if not hits:
            return Coverage(top_score=0.0, n_strong_hits=0)
        top = max(h.score for h in hits)
        n_strong = sum(1 for h in hits if h.score >= strong_ratio * top)
        return Coverage(top_score=float(top), n_strong_hits=int(n_strong))

    return _probe
