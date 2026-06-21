"""Q&A orchestrator: textbook lane (A) + contemporary-literature lane (B), concurrent.

Lane B is strictly additive — any failure yields literature=None and never blocks or
alters Lane A's grounded answer.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)


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


def retrieve_records(question, *, lit_config, client=None, synth_client, cache=None):
    """Lane B retrieval only (no synthesis). Returns (records, search_query).

    records is a list (possibly empty); search_query is the focused query actually used
    (the LLM rewrite on a cache miss, else the deterministic term). Cache key and rewrite
    ordering are preserved from the original build_literature_section so behavior is
    unchanged: rewrite is NOT called on a cache hit."""
    from neuro_caseboard.literature.retriever import (
        LiteratureRetriever, build_query_terms, rewrite_pubmed_query)

    if cache is None:
        from neuro_caseboard.literature.cache import LiteratureCache
        cache = LiteratureCache(lit_config.cache_dir, ttl_days=lit_config.cache_ttl_days)
    term = build_query_terms(question)
    search_query = term
    key = f"{term}|{lit_config.k}|{lit_config.recency_years}|{lit_config.recency_boost}"
    records = cache.get(key)
    if records is None:
        owns_client = client is None
        if client is None:
            from neuro_caseboard.literature.pubmed_client import PubMedClient
            client = PubMedClient(api_key=lit_config.ncbi_api_key)
        # recency_boost is a general ranking knob (default 0 = no-op); applies in both separate and woven modes.
        retriever = LiteratureRetriever(client, k=lit_config.k,
                                        recency_years=lit_config.recency_years,
                                        recency_boost=lit_config.recency_boost)
        search_query = rewrite_pubmed_query(question, synth_client) or term

        async def _retrieve():
            try:
                recs = await retriever.retrieve(question, query=search_query)
                if not recs and search_query != term:
                    recs = await retriever.retrieve(question, query=term)
                return recs
            finally:
                if owns_client:
                    await client.aclose()

        records = asyncio.run(_retrieve())
        cache.set(key, records)  # empty results are cached (records == []) to avoid re-hitting NCBI
    return records, search_query


def build_literature_section(question, *, config=None, lit_config=None,
                             client=None, synth_client=None, cache=None):
    """Run Lane B end to end (separate-block mode). Returns a LiteratureSection or None."""
    from neuro_caseboard.literature.config import load_literature_config
    from neuro_caseboard.literature.synth import synthesize_literature

    lit_config = lit_config or load_literature_config()
    if not lit_config.enabled:
        return None
    try:
        if synth_client is None:
            from neuro_core.config import load_config
            from neuro_core.synth_clients import make_synth_client
            synth_client = make_synth_client(config or load_config())
        records, _ = retrieve_records(question, lit_config=lit_config, client=client,
                                      synth_client=synth_client, cache=cache)
        if not records:
            return None
        syn = synthesize_literature(question, records, synth_client)
        if syn is None:
            return None
        cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                    year=r.year, doi=r.doi, url=r.url)
                 for i, r in enumerate(syn.records, 1)]
        return LiteratureSection(narrative=syn.narrative, citations=cites)
    except Exception:
        _log.debug("literature lane failed", exc_info=True)
        return None


def _retrieve_literature_for_weave(question, *, lit_config, synth_client):
    """Woven Lane B: retrieve + precision-gate. Returns list[LiteratureRecord] (failure-safe → [])."""
    if not lit_config.enabled:
        return []
    try:
        records, search_query = retrieve_records(question, lit_config=lit_config,
                                                 synth_client=synth_client)
        if not records:
            return []
        if lit_config.precision_gate:
            from neuro_caseboard.literature.precision import gate_records
            records = gate_records(records, search_query,
                                   min_overlap=lit_config.precision_min_overlap).records
        return records
    except Exception:
        _log.debug("woven literature retrieval failed", exc_info=True)
        return []


def _answer_question_woven(question, *, config=None, force=False, lit_config=None,
                           synth_client=None, plan_a=None, retrieve_b=None):
    """One woven answer from textbook ([n]) + literature ([L#]). Lane A errors propagate;
    Lane B failures degrade to a textbook-only answer. Mirrors Engine._answer's empty-guard,
    refusal handling, and variant prepend (the woven path bypasses Engine._answer)."""
    from neuro_core.query import Clarification, plan_retrieval, _variant_directive
    from neuro_core.synthesize import REFUSAL, is_refusal
    from neuro_caseboard.woven_synth import synthesize_woven

    if synth_client is None:
        from neuro_core.config import load_config
        from neuro_core.synth_clients import make_synth_client
        synth_client = make_synth_client(config or load_config())
    if plan_a is None:
        def plan_a():
            return plan_retrieval(question, config=config, force=force)
    if retrieve_b is None:
        def retrieve_b():
            return _retrieve_literature_for_weave(question, lit_config=lit_config,
                                                  synth_client=synth_client)

    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(plan_a)
        fb = ex.submit(retrieve_b)
        plan = fa.result()  # Lane A errors propagate (e.g. GpuNotReadyError)
        if isinstance(plan, Clarification):
            return plan
        try:
            records = fb.result()
        except Exception:
            _log.debug("woven literature lane raised in executor", exc_info=True)
            records = []

    directive = _variant_directive(plan.variant.label) if plan.variant else None

    def _synth():
        return synthesize_woven(plan.question, plan.hits, plan.figures, plan.images,
                                records, synth_client, variant_directive=directive)

    syn = _synth()
    # Empty-answer guard (parity with Engine._answer / TKT-C5): a transient empty/whitespace
    # result is not a refusal; retry once, then degrade to the honest REFUSAL so the caller
    # never receives a blank, not-gradable answer.
    if not (syn.answer or "").strip():
        syn = _synth()
        if not (syn.answer or "").strip():
            return QAResult(answer=REFUSAL, citations=[], figures=[], literature=None)
    if is_refusal(syn.answer):
        # Abstention: figures/citations/literature collected from retrieval are spurious.
        return QAResult(answer=syn.answer, citations=[], figures=[], literature=None)

    answer = syn.answer
    if plan.variant is not None:
        answer = (f"**Assuming {plan.variant.label} (most consistent with retrieved "
                  "sources).**\n\n" + answer)

    lit = None
    if syn.records:
        cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                    year=r.year, doi=r.doi, url=r.url)
                 for i, r in enumerate(syn.records, 1)]
        lit = LiteratureSection(narrative="", citations=cites)
    return QAResult(answer=answer, citations=syn.citations, figures=plan.figures,
                    literature=lit)


def answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None) -> QAResult:
    """Run Lane A and Lane B concurrently. Lane A errors propagate; Lane B failures drop
    the section. `lane_a`/`lane_b` are injectable no-arg callables (for tests).

    When `LITERATURE_WEAVE` is on and no lanes are injected, delegates to the woven
    orchestrator (_answer_question_woven) which produces one integrated answer."""
    # Woven mode (flag-gated): one integrated answer. Only when no lanes were injected, so
    # the separate-path tests (which inject lane_a/lane_b) are unaffected.
    if lane_a is None and lane_b is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
        if lit_config.weave:
            return _answer_question_woven(question, config=config, force=force,
                                          lit_config=lit_config)

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
        # Lane A errors propagate (e.g. GpuNotReadyError); the executor __exit__ then
        # waits for Lane B to finish on shutdown — acceptable since Lane B catches its
        # own exceptions and Lane A failures are rare.
        qr = fa.result()
        # An ambiguous query short-circuits: a Clarification has no answer to attach a
        # literature section to, so pass it straight back for the caller (CLI/app) to handle.
        from neuro_core.query import Clarification
        if isinstance(qr, Clarification):
            return qr
        try:
            lit = fb.result()
        except Exception:
            _log.debug("literature lane raised in executor", exc_info=True)
            lit = None
    return QAResult(answer=qr.answer, citations=qr.citations,
                    figures=qr.figures, literature=lit)
