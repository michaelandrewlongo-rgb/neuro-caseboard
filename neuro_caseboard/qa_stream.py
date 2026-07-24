"""Streaming Ask orchestrator: emit retrieval (sources/figures) first, then woven-synthesis
token deltas, then literature/verification. Mirrors qa._answer_question_woven's retrieval,
empty-guard, refusal, and variant handling — but streams the synthesis call.

`emit` receives domain event dicts (values may be domain objects); serialization to the wire
shape lives in the API layer (api.server._serialize_ask_event)."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

from neuro_caseboard.qa import (LiteratureSection, LiteratureCitation,
                                _retrieve_literature_for_weave)

_log = logging.getLogger(__name__)


def _emit_batch(emit, qr):
    """Emit a completed QAResult (from the blocking fallback) as one batch + done."""
    emit({"type": "sources", "citations": list(qr.citations or [])})
    emit({"type": "figures", "figures": list(qr.figures or [])})
    emit({"type": "answer", "answer": qr.answer, "citations": list(qr.citations or []),
          "figures": list(qr.figures or []), "refusal": False})
    emit({"type": "literature", "literature": getattr(qr, "literature", None)})
    emit({"type": "corpus", "corpus": list(getattr(qr, "corpus", None) or [])})
    emit({"type": "verification", "verification": getattr(qr, "verification", None)})
    emit({"type": "done"})


def _fallback(question, emit, *, config, force, skip_disambiguation):
    from neuro_caseboard.qa import answer_question
    from neuro_core.query import Clarification
    qr = answer_question(question, config=config, force=force,
                         skip_disambiguation=skip_disambiguation)
    if isinstance(qr, Clarification):
        emit({"type": "clarification", "question": getattr(qr, "question", question),
              "variants": list(getattr(qr, "variants", []))})
        emit({"type": "done"})
        return
    _emit_batch(emit, qr)


def stream_answer(question, emit, *, config=None, force=False, skip_disambiguation=False,
                  lit_config=None, synth_client=None, plan_a=None, retrieve_b=None,
                  retrieve_c=None, corpus_config=None, corpus_query=None, style=None):
    from neuro_core.query import Clarification, _variant_directive
    from neuro_core.synthesize import REFUSAL, is_refusal, build_citations
    from neuro_caseboard.woven_synth import build_woven_prompt, build_woven_system

    if lit_config is None and plan_a is None and retrieve_b is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
        if not lit_config.weave:                       # separate-lane config → blocking fallback
            _fallback(question, emit, config=config, force=force,
                      skip_disambiguation=skip_disambiguation)
            return

    try:
        if synth_client is None:
            from neuro_core.config import load_config
            from neuro_core.synth_clients import make_synth_client
            synth_client = make_synth_client(config or load_config())
        if plan_a is None:
            from neuro_core.query import plan_retrieval
            def plan_a():
                return plan_retrieval(question, config=config, force=force,
                                      skip_disambiguation=skip_disambiguation)
        if retrieve_b is None:
            def retrieve_b():
                return _retrieve_literature_for_weave(question, lit_config=lit_config,
                                                      synth_client=synth_client)
        if retrieve_c is None:
            from neuro_caseboard.corpus import load_corpus_config, retrieve_corpus_for_weave
            cc = corpus_config if corpus_config is not None else load_corpus_config()
            _cq = corpus_query or question  # clinical query decouples corpus FTS from framing
            def retrieve_c():
                return retrieve_corpus_for_weave(_cq, cc)

        with ThreadPoolExecutor(max_workers=3) as ex:
            fa = ex.submit(plan_a)
            fb = ex.submit(retrieve_b)
            fc = ex.submit(retrieve_c)                  # Lane C (corpus): failure-safe → []
            plan = fa.result()                          # Lane A errors propagate
            if isinstance(plan, Clarification):
                emit({"type": "clarification",
                      "question": getattr(plan, "question", question),
                      "variants": list(getattr(plan, "variants", []))})
                emit({"type": "done"})
                return
            try:
                records = fb.result()
            except Exception:
                _log.debug("woven literature lane raised", exc_info=True)
                records = []
            try:
                corpus_records = fc.result()
            except Exception:
                _log.debug("woven corpus lane raised", exc_info=True)
                corpus_records = []

        citations = build_citations(plan.hits, plan.figures)
        emit({"type": "sources", "citations": citations})
        emit({"type": "figures", "figures": list(plan.figures or [])})

        directive = _variant_directive(plan.variant.label) if plan.variant else None
        prefix = ""
        if plan.variant is not None:
            prefix = (f"**Assuming {plan.variant.label} (most consistent with retrieved "
                      "sources).**\n\n")
            emit({"type": "answer_delta", "text": prefix})

        system = build_woven_system(corpus_records, style)
        route = "ask.stream.extract" if style == "extract" else "ask.stream"

        def _stream_body():
            user = build_woven_prompt(plan.question, plan.hits, plan.figures, records, directive,
                                      corpus_records=corpus_records)
            parts = []
            for delta in synth_client.generate_stream(system, user, plan.images, route=route):
                if not delta:
                    continue
                parts.append(delta)
                emit({"type": "answer_delta", "text": delta})
            return "".join(parts)

        body = _stream_body()
        # Empty-answer guard (parity with _answer_question_woven): retry once, then REFUSAL.
        if not body.strip():
            body = _stream_body()
            if not body.strip():
                emit({"type": "answer", "answer": REFUSAL, "citations": [], "figures": [],
                      "refusal": True})
                emit({"type": "literature", "literature": None})
                emit({"type": "corpus", "corpus": []})
                emit({"type": "verification", "verification": None})
                emit({"type": "done"})
                return

        full_answer = prefix + body
        if is_refusal(body):
            # Abstention: retrieval-derived sources/figures/literature/corpus are spurious.
            emit({"type": "answer", "answer": body, "citations": [], "figures": [],
                  "refusal": True})
            emit({"type": "literature", "literature": None})
            emit({"type": "corpus", "corpus": []})
            emit({"type": "verification", "verification": None})
            emit({"type": "done"})
            return

        emit({"type": "answer", "answer": full_answer, "citations": citations,
              "figures": list(plan.figures or []), "refusal": False})

        lit = None
        if records:
            cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                        year=r.year, doi=r.doi, url=r.url,
                                        abstract=getattr(r, "abstract", "") or "")
                     for i, r in enumerate(records, 1)]
            lit = LiteratureSection(narrative="", citations=cites)
        emit({"type": "literature", "literature": lit})
        emit({"type": "corpus", "corpus": list(corpus_records or [])})

        from neuro_caseboard.answer_verify import verify_answer
        premises = {str(getattr(c, "n", i)): getattr(c, "text", "") or ""
                    for i, c in enumerate(citations, 1)}
        for i, r in enumerate(records or [], 1):
            premises[f"L{i}"] = getattr(r, "abstract", "") or ""
        for i, r in enumerate(corpus_records or [], 1):
            premises[f"D{i}"] = getattr(r, "content", "") or ""
        emit({"type": "verification", "verification": verify_answer(full_answer, premises)})
        # §3.3 quoted-span sidecar + §5 Decision Card (parity with _answer_question_woven): opt-in,
        # additive. Reuses the in-scope synth_client + premises; a failure returns [] / a prose-only
        # card and never blocks the stream. DECISION_CARD implies the spans (the gate needs them).
        def _flag(name):
            return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")
        spans = []
        if _flag("EVIDENCE_SPANS") or _flag("DECISION_CARD"):
            from neuro_caseboard.evidence_spans import extract_and_verify
            spans = extract_and_verify(full_answer, premises, synth_client)
        if _flag("EVIDENCE_SPANS"):
            emit({"type": "evidence", "evidence_spans": spans})
        if _flag("DECISION_CARD"):
            from datetime import date
            from neuro_caseboard.claim_review import build_decision_card
            marker_year = {}
            for i, r in enumerate(records or [], 1):
                marker_year[f"L{i}"] = getattr(r, "year", None)
            for i, r in enumerate(corpus_records or [], 1):
                marker_year[f"D{i}"] = getattr(r, "year", None)
            try:
                staleness_years = int(os.environ.get("STALENESS_YEARS") or 5)
            except ValueError:
                staleness_years = 5
            emit({"type": "decision", "decision_card": build_decision_card(
                full_answer, spans=spans, marker_year=marker_year, now_year=date.today().year,
                question=question, staleness_years=staleness_years)})
        emit({"type": "done"})
    except Exception:
        # Any streaming-path failure degrades to the proven blocking path (still persisted).
        _log.debug("stream_answer failed; falling back to blocking answer_question", exc_info=True)
        _fallback(question, emit, config=config, force=force,
                  skip_disambiguation=skip_disambiguation)
