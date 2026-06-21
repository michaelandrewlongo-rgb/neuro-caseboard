"""Deterministic topical-relevance gate applied to ranked literature BEFORE woven synthesis.

Weaving literature inline makes off-topic "citation noise" more damaging than it is in a
siloed block, so this gate drops records that don't share the query's core concepts. Pure:
no network, no LLM. Concepts come from the same tokenizer the retriever uses for fallback
queries (build_query_terms), so the gate sees the same vocabulary the search did."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateResult:
    records: list = field(default_factory=list)
    note: str = ""


def _concepts(query: str) -> set:
    from neuro_caseboard.literature.retriever import build_query_terms
    return set(build_query_terms(query, max_terms=20).split())


def gate_records(records: list, query: str, *, min_overlap: int = 1,
                 rank_ceiling: int | None = None) -> GateResult:
    """Keep records whose title+abstract shares >= min_overlap concept tokens with the query.

    Empty input -> empty result. No extractable concepts -> pass-through (never gate to empty
    on a degenerate query). Empty after gating -> keep the single most-relevant (first) record
    with a caution note, mirroring standardize_records' thin-coverage fallback."""
    if not records:
        return GateResult(records=[], note="")
    pool = records if rank_ceiling is None else records[:rank_ceiling]
    concepts = _concepts(query)
    if not concepts:
        return GateResult(records=list(pool), note="")
    kept = []
    for r in pool:
        hay = f"{r.title} {r.abstract}".lower()
        if sum(1 for c in concepts if c in hay) >= min_overlap:
            kept.append(r)
    if kept:
        return GateResult(records=kept, note="")
    return GateResult(records=list(pool[:1]),
                      note="No literature passed the topical relevance gate; showing the "
                           "single most relevant article — interpret with caution.")
