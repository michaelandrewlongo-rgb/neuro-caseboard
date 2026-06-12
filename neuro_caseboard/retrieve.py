"""Retriever wiring for the live pipeline.

Deliberately avoids caseprep's heavy lanes (SemanticCorpusRetriever / board_cards need a
pgvector DB that may be unavailable and blocks for a long time). Uses the offline FTS5
``CorpusRetriever``, plus an optional textbook lane: in-process via textbook-rag's
``engine.query.search`` when importable, else the subprocess ``TextbookRetriever`` when
the ``textbook-rag`` CLI is on PATH. Any lane that fails to construct is simply skipped.
"""

from __future__ import annotations

import os
import shutil


import re

# Tiny stoplist so FTS5 queries keep the informative clinical terms.
_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "are", "any", "its",
    "confirm", "identify", "which", "what", "when", "before", "after", "into",
    "relative", "during", "case", "patient", "plan", "vs", "or", "of", "to", "in",
    "on", "at", "is", "be", "if", "a", "an",
}


class _SanitizingCorpus:
    """Wrap caseprep's FTS5 CorpusRetriever so query punctuation/operators can't trip
    the MATCH parser. caseprep passes the raw question (which contains '?', '/', '(',
    '->', '>=') straight into FTS5; we reduce it to bare informative terms first."""

    def __init__(self, inner, *, max_terms: int = 6):
        self._inner = inner
        self._max_terms = max_terms

    @staticmethod
    def _clean(query: str, max_terms: int) -> str:
        terms: list[str] = []
        for tok in re.findall(r"[A-Za-z0-9]+", (query or "").lower()):
            if len(tok) < 3 or tok in _STOP or tok in terms:
                continue
            terms.append(tok)
            if len(terms) >= max_terms:
                break
        return " ".join(terms)

    def retrieve(self, query, *, top_n: int = 5, subdomain=None):
        cleaned = self._clean(query, self._max_terms)
        if not cleaned:
            return []
        try:
            return self._inner.retrieve(cleaned, top_n=top_n)
        except Exception:
            return []


def _corpus_lane():
    try:
        from caseprep.retrievers.corpus import CorpusRetriever
        return _SanitizingCorpus(CorpusRetriever())
    except Exception:
        return None


def _cite(hit) -> str:
    book = hit.get("book") or ""
    pp = hit.get("printed_page") or hit.get("page")
    return f"{book}, p.{pp}" if book else ""


class InProcessTextbookRetriever:
    """Normalise textbook-rag in-process search hits into EvidenceRecords (metadata
    intact, so figures/folios survive for figure->claim linkage)."""

    def __init__(self, search_fn):
        self._search = search_fn

    def retrieve(self, query, *, subdomain=None, top_n=6):
        from caseprep.core.contracts import EvidenceRecord
        hits = self._search(query, top_n) or []
        out = []
        for h in list(hits)[:top_n]:
            book = h.get("book") or ""
            page = h.get("page")
            if not book or page is None:
                continue
            meta = {
                "book": book, "chapter": h.get("chapter") or "", "page": page,
                "printed_page": h.get("printed_page"), "score": h.get("score"),
                "citation": _cite(h), "retrieval_source": "textbook_rag_inproc",
            }
            if h.get("figure_path"):
                meta["figure_path"] = h["figure_path"]
                meta["caption"] = h.get("caption") or ""
            out.append(EvidenceRecord(
                id=f"textbook-{book}-p{page}", source="textbook",
                title=f"{book} (p.{h.get('printed_page') or page})",
                text=h.get("text") or "", metadata=meta))
        return out


def _textbook_lane(enable: bool):
    if not enable:
        return None
    try:  # in-process (textbook-rag importable as a library on its seam branch)
        from engine.query import search as tb_search  # type: ignore
        return InProcessTextbookRetriever(lambda q, k: tb_search(q, k))
    except Exception:
        pass
    try:  # subprocess CLI fallback
        if shutil.which(os.environ.get("TEXTBOOK_RAG_BIN", "textbook-rag")):
            from caseprep.retrievers.textbook import TextbookRetriever
            return TextbookRetriever()
    except Exception:
        pass
    return None


def build_retriever(*, enable_corpus: bool = True, enable_textbook=None):
    """Compose the available retrieval lanes, or return None when none are available."""
    if enable_textbook is None:
        enable_textbook = os.environ.get("CASEPREP_TEXTBOOK", "0") == "1"
    lanes = []
    if enable_corpus:
        c = _corpus_lane()
        if c is not None:
            lanes.append(c)
    t = _textbook_lane(enable_textbook)
    if t is not None:
        lanes.append(t)
    if not lanes:
        return None
    if len(lanes) == 1:
        return lanes[0]
    from caseprep.retrievers.composite import CompositeRetriever
    return CompositeRetriever(lanes)
