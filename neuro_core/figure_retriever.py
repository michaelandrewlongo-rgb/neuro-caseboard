"""Unified figure-retrieval lane: one IDF caption-lexical ranker (prefers the Gemini
caption) + an optional BiomedCLIP semantic lane (RRF-fused), with region/level/domain
guards applied ONLY when a topic is supplied (boards) and skipped for free-text Q&A."""
from __future__ import annotations

import collections
import math
import os
from dataclasses import dataclass

from neuro_core.figure_guards import (
    _cap_toks, _caption_head, _expand_terms, _VIGNETTE, _FLOWCHART, figure_offtarget,
    _DIAGNOSTIC_BOOKS,
)


def _row_caption(row):
    """Effective caption for a figure row: the Gemini caption (larger cap, pure signal) when
    present, else the source caption (tighter cap to fight legend bloat)."""
    gem = (row.get("gemini_caption") or "").strip()
    if gem:
        return _caption_head(gem, 700)
    return _caption_head((row.get("caption") or "").strip())


@dataclass
class FigureHit:
    """One ranked figure. NOTE: ``score`` is on different scales depending on the lanes used —
    a raw IDF-TF sum when lexical-only, or a small reciprocal-rank-fusion value (~0.01-0.02)
    when the semantic lane is active. Use it for ordering within one query, not as an absolute
    threshold across configurations."""
    book: str
    page: int
    figure_path: str
    caption: str
    score: float = 0.0
    chapter: str | None = None
    context: str = ""
    vector: object = None


def _fuse(lex, sem, top_n, *, k: int = 60):
    scores: dict = {}
    rowmap: dict = {}
    for rank, (_s, row) in enumerate(lex):
        key = row["figure_path"]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        rowmap[key] = row
    for rank, (_s, row) in enumerate(sem):
        key = row["figure_path"]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        rowmap[key] = row
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(rowmap[key], sc) for key, sc in ranked[:top_n]]


class FigureRetriever:
    def __init__(self, rows, *, embed_fn=None):
        self._rows = rows
        self._embed_fn = embed_fn
        df = collections.Counter()
        for row in rows:
            for t in set(_cap_toks(row["caption"])):
                df[t] += 1
        self._df = df
        self._n = max(1, len(rows))
        # interface parity with the old CaptionIndex: the Q&A engine uses this to display the
        # richer caption for any figure, even ones surfaced by the text/visual lanes.
        self.caption_by_path = {r["figure_path"]: r["caption"] for r in rows}

    def _idf(self, t: str) -> float:
        return math.log((self._n + 1) / (self._df.get(t, 0) + 1))

    def _lexical(self, qterms, candidates):
        scored = []
        for row in candidates:
            ct = collections.Counter(_cap_toks(row["caption"]))
            matched = [t for t in qterms if t in ct]
            if len(matched) < 2:
                continue
            s = sum(ct[t] * self._idf(t) for t in matched)
            cap_low = row["caption"].lower()
            if _VIGNETTE.search(row["caption"]):
                s *= 0.4
            if any(f in cap_low for f in _FLOWCHART):
                s *= 0.35
            if s > 0:
                scored.append((s, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _semantic(self, query, candidates):
        if not self._embed_fn:
            return []
        try:
            import numpy as np
            qv = np.asarray(self._embed_fn(query), dtype="float32").ravel()
        except Exception:
            return []
        qn = float(np.linalg.norm(qv)) or 1.0
        sims = []
        for row in candidates:
            v = row.get("vector")
            if v is None:
                continue
            v = np.asarray(v, dtype="float32").ravel()
            if v.size != qv.size:
                continue
            vn = float(np.linalg.norm(v)) or 1.0
            sims.append((float(qv @ v) / (qn * vn), row))
        sims.sort(key=lambda x: x[0], reverse=True)
        return sims

    def retrieve(self, query, *, topic: str = "", top_n: int = 8, guard_set: str = "full"):
        qterms = _expand_terms(set(_cap_toks(query)))
        if not qterms:
            return []
        if topic:
            candidates = [r for r in self._rows
                          if not figure_offtarget(r["caption"], topic, r.get("book", ""),
                                                  r.get("context", ""), guards=guard_set)]
        else:
            candidates = list(self._rows)
        lex = self._lexical(qterms, candidates)
        sem = self._semantic(query, candidates)
        ordered = _fuse(lex, sem, top_n) if sem else [(row, s) for s, row in lex[:top_n]]
        return [FigureHit(book=row.get("book", ""), page=row.get("page"),
                          figure_path=row["figure_path"], caption=row["caption"],
                          chapter=row.get("chapter"), context=row.get("context", ""),
                          vector=row.get("vector"), score=round(float(s), 4))
                for row, s in ordered]


_ROWS_CACHE = None


def _load_rows(index_dir=None):
    """Load figure rows from figures.lance once (first-call-wins, process-scoped cache; the
    index location is fixed for a process). Effective caption = gemini_caption if present else
    source caption (gemini larger cap, source tighter). Diagnostic books skipped."""
    global _ROWS_CACHE
    if _ROWS_CACHE is not None:
        return _ROWS_CACHE
    from neuro_core.config import load_config
    index_dir = index_dir or str(load_config().index_dir)
    rows_out = []
    if os.path.isdir(index_dir):
        import lancedb
        db = lancedb.connect(index_dir)
        names = set(db.table_names())
        if "figures" in names:
            for r in db.open_table("figures").search().limit(10**6).to_list():
                fp = r.get("figure_path") or ""
                book = r.get("book") or ""
                if any(d in book.lower() for d in _DIAGNOSTIC_BOOKS):
                    continue
                cap = _row_caption(r)
                if cap and fp and os.path.isfile(fp):
                    rows_out.append({"book": book, "chapter": r.get("chapter"),
                                     "page": r.get("page"), "figure_path": fp,
                                     "caption": cap, "context": "", "vector": r.get("vector")})
            if rows_out and "chunks" in names:
                ctx = {}
                for r in db.open_table("chunks").search().limit(10**6).to_list():
                    t = (r.get("text") or "").strip()
                    if t:
                        kk = (r.get("book") or "", str(r.get("page")))
                        ctx[kk] = (ctx.get(kk, "") + " " + t)[:6000]
                for row in rows_out:
                    row["context"] = ctx.get((row["book"], str(row["page"])), "")
    _ROWS_CACHE = rows_out
    return rows_out


def build_figure_retriever(index_dir=None, *, embed_fn=None):
    rows = _load_rows(index_dir)
    if not rows:
        return None
    return FigureRetriever(rows, embed_fn=embed_fn)
