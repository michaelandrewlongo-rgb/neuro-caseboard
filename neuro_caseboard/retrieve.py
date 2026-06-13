"""Retriever wiring for the live pipeline.

Deliberately avoids caseprep's heavy lanes (SemanticCorpusRetriever / board_cards need a
pgvector DB that may be unavailable and blocks for a long time). Uses the offline FTS5
``CorpusRetriever``, plus an optional textbook lane: in-process via textbook-rag's
no-GPU lexical ``engine.index.Index.text_search`` when the repo + LanceDB index are
present, else the subprocess ``TextbookRetriever`` when the ``textbook-rag`` CLI is on
PATH. Any lane that fails to construct is simply skipped.

The textbook lane is enabled with ``CASEPREP_TEXTBOOK=1``; the repo and index locations
default to ``/home/michael/neuro-textbook-rag`` and ``<repo>/index`` and are overridable
via ``TEXTBOOK_RAG_REPO`` / ``TEXTBOOK_INDEX_DIR``.
"""

from __future__ import annotations

import os
import shutil
import sys


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


def _default_textbook_repo() -> str:
    return os.environ.get("TEXTBOOK_RAG_REPO") or "/home/michael/neuro-textbook-rag"


def _default_index_dir() -> str:
    return os.environ.get("TEXTBOOK_INDEX_DIR") or os.path.join(_default_textbook_repo(), "index")


def _hit_to_dict(h) -> dict:
    """Convert a textbook-rag ``Hit`` to the dict shape InProcessTextbookRetriever wants.

    Figures are intentionally omitted in this lexical v1 (the index stores PDF ``page``
    only, no ``printed_page``; figure->claim linkage is a later visual-lane concern)."""
    return {
        "book": getattr(h, "book", "") or "",
        "chapter": getattr(h, "chapter", None),
        "page": getattr(h, "page", None),
        "printed_page": None,            # index has PDF page only
        "score": getattr(h, "score", None),
        "text": getattr(h, "text", "") or "",
    }


def _index_search_fn(*, index_dir: str | None = None, repo: str | None = None):
    """A no-GPU lexical ``search_fn(query, k) -> list[dict]`` backed by textbook-rag's
    ``Index.text_search``, or ``None`` when the engine or LanceDB index are unavailable."""
    repo = repo or _default_textbook_repo()
    index_dir = index_dir or _default_index_dir()
    if not os.path.isdir(index_dir):
        return None
    if repo and os.path.isdir(repo) and repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        from engine.index import Index  # type: ignore
        index = Index(index_dir)
    except Exception:
        return None

    def search_fn(query, k):
        terms = _SanitizingCorpus._clean(query, 8)   # FTS-safe bare clinical terms
        if not terms:
            return []
        try:
            hits = index.text_search(terms, k) or []
        except Exception:
            return []
        return [_hit_to_dict(h) for h in hits]

    return search_fn


def _textbook_lane(enable: bool):
    if not enable:
        return None
    try:  # in-process lexical lane (textbook-rag Index.text_search, no GPU)
        fn = _index_search_fn()
        if fn is not None:
            return InProcessTextbookRetriever(fn)
    except Exception:
        pass
    try:  # legacy in-process entrypoint, if a build ever exposes engine.query.search
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
