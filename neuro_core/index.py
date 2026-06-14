from dataclasses import dataclass
from typing import Optional

import lancedb

TABLE = "chunks"


@dataclass
class Hit:
    id: str
    book: str
    chapter: Optional[str]
    page: int
    text: str
    score: float = 0.0
    has_figure: bool = False
    caption: Optional[str] = None
    figure_path: Optional[str] = None


def reciprocal_rank_fusion(rankings, k=60):
    """rankings: list of id-lists, each ordered best-first.
    Returns [(id, fused_score)] sorted descending."""
    scores = {}
    for ranking in rankings:
        for rank, _id in enumerate(ranking):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def build_index(chunks, embedder, index_dir, batch_size=256, on_progress=None):
    db = lancedb.connect(str(index_dir))
    texts = [c.text for c in chunks]
    vectors = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(embedder.embed_texts(texts[i:i + batch_size]))
        if on_progress:
            on_progress(min(i + batch_size, len(texts)), len(texts))
    rows = []
    for c, v in zip(chunks, vectors):
        rows.append({
            "id": c.id,
            "book": c.book,
            "chapter": c.chapter or "",
            "page": int(c.page),
            "text": c.text,
            "vector": [float(x) for x in v],
            "has_figure": bool(c.has_figure),
            "caption": c.caption or "",
            "figure_path": c.figure_path or "",
        })
    tbl = db.create_table(TABLE, data=rows, mode="overwrite")
    tbl.create_fts_index("text", replace=True)
    return tbl


class Index:
    def __init__(self, index_dir):
        self.db = lancedb.connect(str(index_dir))
        self.tbl = self.db.open_table(TABLE)

    def _row_to_hit(self, row):
        return Hit(
            id=row["id"], book=row["book"],
            chapter=row["chapter"] or None, page=int(row["page"]),
            text=row["text"],
            has_figure=bool(row.get("has_figure", False)),
            caption=(row.get("caption") or None),
            figure_path=(row.get("figure_path") or None),
        )

    def vector_search(self, query_vector, k):
        rows = self.tbl.search([float(x) for x in query_vector]).limit(k).to_list()
        return [self._row_to_hit(r) for r in rows]

    def text_search(self, query_text, k):
        rows = self.tbl.search(query_text, query_type="fts").limit(k).to_list()
        return [self._row_to_hit(r) for r in rows]

    def hybrid_search(self, query_text, query_vector, k):
        vhits = self.vector_search(query_vector, k)
        thits = self.text_search(query_text, k)
        by_id = {h.id: h for h in vhits + thits}
        fused = reciprocal_rank_fusion(
            [[h.id for h in vhits], [h.id for h in thits]]
        )
        out = []
        for _id, score in fused[:k]:
            hit = by_id[_id]
            hit.score = score
            out.append(hit)
        return out
