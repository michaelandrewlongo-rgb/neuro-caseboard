"""Q&A orchestrator: textbook lane (A) + contemporary-literature lane (B), concurrent.

Lane B is strictly additive — any failure yields literature=None and never blocks or
alters Lane A's grounded answer.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field


@dataclass
class LiteratureCitation:
    n: int
    pmid: str
    title: str
    journal: str
    year: int | None
    doi: str
    url: str


@dataclass
class LiteratureSection:
    narrative: str
    citations: list = field(default_factory=list)


@dataclass
class QAResult:
    answer: str
    citations: list = field(default_factory=list)
    figures: list = field(default_factory=list)
    literature: "LiteratureSection | None" = None


def build_literature_section(question, *, config=None, lit_config=None,
                             client=None, synth_client=None, cache=None):
    """Run Lane B end to end. Returns a LiteratureSection or None (disabled/empty/error)."""
    from neuro_caseboard.literature.config import load_literature_config
    from neuro_caseboard.literature.retriever import LiteratureRetriever, build_query_terms
    from neuro_caseboard.literature.synth import synthesize_literature

    lit_config = lit_config or load_literature_config()
    if not lit_config.enabled:
        return None
    try:
        if cache is None:
            from neuro_caseboard.literature.cache import LiteratureCache
            cache = LiteratureCache(lit_config.cache_dir, ttl_days=lit_config.cache_ttl_days)
        term = build_query_terms(question)
        key = f"{term}|{lit_config.k}|{lit_config.recency_years}"
        records = cache.get(key)
        if records is None:
            if client is None:
                from neuro_caseboard.literature.pubmed_client import PubMedClient
                client = PubMedClient(api_key=lit_config.ncbi_api_key)
            retriever = LiteratureRetriever(client, k=lit_config.k,
                                            recency_years=lit_config.recency_years)
            records = asyncio.run(retriever.retrieve(question))
            cache.set(key, records)
        if not records:
            return None
        if synth_client is None:
            from neuro_core.config import load_config
            from neuro_core.synth_clients import make_synth_client
            synth_client = make_synth_client(config or load_config())
        syn = synthesize_literature(question, records, synth_client)
        if syn is None:
            return None
        cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                    year=r.year, doi=r.doi, url=r.url)
                 for i, r in enumerate(syn.records, 1)]
        return LiteratureSection(narrative=syn.narrative, citations=cites)
    except Exception:
        return None


def answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None) -> QAResult:
    """Run Lane A and Lane B concurrently. Lane A errors propagate; Lane B failures drop
    the section. `lane_a`/`lane_b` are injectable no-arg callables (for tests)."""
    if lane_a is None:
        from neuro_core.query import query
        def lane_a():
            return query(question, config=config, force=force)
    if lane_b is None:
        def lane_b():
            return build_literature_section(question, config=config)

    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(lane_a)
        fb = ex.submit(lane_b)
        qr = fa.result()  # propagate Lane A errors (e.g. GpuNotReadyError)
        try:
            lit = fb.result()
        except Exception:
            lit = None
    return QAResult(answer=qr.answer, citations=qr.citations,
                    figures=qr.figures, literature=lit)
