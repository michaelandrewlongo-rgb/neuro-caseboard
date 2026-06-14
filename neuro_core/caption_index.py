"""Lexical figure-retrieval lane over each figure's own caption.

The page-text lane drifts within the right topic (a distal-M4 page for an M1 question) and the
BiomedCLIP image lane is too coarse for fine neuroanatomy; both miss the plate that actually
NAMES the queried structures. This lane ranks figures by IDF-weighted overlap of the question
with each figure's caption — preferring the Gemini multimodal caption (which names the specific
arteries/branches, nerves, landmarks) and falling back to the source caption. No GPU.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import lancedb

from .index import Hit
from .visual_index import FIGURES_TABLE

_TOK = re.compile(r"[a-z0-9]+")


def _toks(s):
    return [t for t in _TOK.findall((s or "").lower()) if len(t) > 2]


def rank_captions(rows, query, k):
    """Pure ranking: rows are dicts carrying an effective ``caption``. Returns up to ``k``
    ``(score, row)`` best-first, scored by IDF-weighted overlap of the query terms with the
    caption. Requires >=2 distinct matched terms so a single shared common word can't surface
    an unrelated plate."""
    qterms = set(_toks(query))
    if not qterms or not rows:
        return []
    n = max(1, len(rows))
    df = Counter()
    for r in rows:
        for t in set(_toks(r["caption"])):
            df[t] += 1

    def idf(t):
        return math.log((n + 1) / (df.get(t, 0) + 1))

    scored = []
    for r in rows:
        ct = Counter(_toks(r["caption"]))
        matched = [t for t in qterms if t in ct]
        if len(matched) < 2:
            continue
        s = sum(ct[t] * idf(t) for t in matched)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


class CaptionIndex:
    """Loads the ``figures`` table once and serves the caption-lexical lane. ``caption_search``
    returns ``Hit`` objects (so the query engine can fuse them with the text and visual lanes by
    ``figure_path``); ``caption_by_path`` lets the engine display the richer caption for any
    figure, even ones surfaced by another lane."""

    def __init__(self, index_dir):
        tbl = lancedb.connect(str(index_dir)).open_table(FIGURES_TABLE).to_arrow()
        names = set(tbl.schema.names)
        book = tbl.column("book").to_pylist()
        chapter = tbl.column("chapter").to_pylist() if "chapter" in names else [None] * tbl.num_rows
        page = tbl.column("page").to_pylist()
        fpath = tbl.column("figure_path").to_pylist()
        src = tbl.column("caption").to_pylist() if "caption" in names else [""] * tbl.num_rows
        gem = tbl.column("gemini_caption").to_pylist() if "gemini_caption" in names else None
        self.rows = []
        for i in range(tbl.num_rows):
            cap = ((gem[i] if gem and gem[i] else src[i]) or "").strip()
            fp = fpath[i]
            if cap and fp:
                self.rows.append({"book": book[i] or "", "chapter": chapter[i],
                                  "page": int(page[i]), "figure_path": fp, "caption": cap})
        self.caption_by_path = {r["figure_path"]: r["caption"] for r in self.rows}

    def caption_search(self, query, k):
        out = []
        for s, r in rank_captions(self.rows, query, k):
            out.append(Hit(id=f'cap-{r["book"]}-p{r["page"]}', book=r["book"],
                           chapter=r["chapter"] or None, page=r["page"], text=r["caption"],
                           score=float(s), has_figure=True, caption=r["caption"],
                           figure_path=r["figure_path"]))
        return out
