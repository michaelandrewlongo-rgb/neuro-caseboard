"""Standalone board-review card lane (`cards` table).

A second LanceDB table that lives in the same INDEX_DIR as `chunks` and
`figures`, but holds Q&A board-review cards (e.g. the SANS / ABNS Anki deck)
instead of textbook prose. It deliberately mirrors `neuro_core/index.py` so the
SAME Embedder, the SAME BGE-large-en-v1.5 vectors, and the SAME FTS + vector +
RRF hybrid-search machinery apply with zero new infrastructure.

Install: copy this file to  neuro_core/cards_index.py
Build:   python -m neuro_core.scripts.build_cards_index
Query:   neuro_core.cards_query.cards_query("...")
"""

from dataclasses import dataclass, field
from typing import List

import lancedb

from .index import reciprocal_rank_fusion

CARDS_TABLE = "cards"


@dataclass
class CardHit:
    id: str
    question_text: str
    answer_text: str
    deck_name: str = ""
    deck_full: str = ""
    tags: str = ""
    model_name: str = ""
    question_html: str = ""
    answer_html: str = ""
    image_paths: List[str] = field(default_factory=list)
    text: str = ""
    score: float = 0.0


def build_cards_index(cards, embedder, index_dir, batch_size=256, on_progress=None):
    """Embed and write the `cards` table.

    `cards` is a list of dicts with at least: id, question_text, answer_text, text.
    Optional: deck_name, deck_full, tags, model_name, question_html, answer_html,
    image_paths (list[str]). The `text` field is what gets embedded + FTS-indexed.
    """
    db = lancedb.connect(str(index_dir))
    texts = [c["text"] for c in cards]

    vectors = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(embedder.embed_texts(texts[i:i + batch_size]))
        if on_progress:
            on_progress(min(i + batch_size, len(texts)), len(texts))

    rows = []
    for c, v in zip(cards, vectors):
        rows.append({
            "id": c["id"],
            "question_text": c.get("question_text", ""),
            "answer_text": c.get("answer_text", ""),
            "deck_name": c.get("deck_name", ""),
            "deck_full": c.get("deck_full", ""),
            "tags": c.get("tags", ""),
            "model_name": c.get("model_name", ""),
            "question_html": c.get("question_html", ""),
            "answer_html": c.get("answer_html", ""),
            "image_paths": list(c.get("image_paths", []) or []),
            "text": c["text"],
            "vector": [float(x) for x in v],
        })

    tbl = db.create_table(CARDS_TABLE, data=rows, mode="overwrite")
    tbl.create_fts_index("text", replace=True)
    return tbl


class CardsIndex:
    """Hybrid (vector + FTS, RRF-fused) search over the `cards` table.

    Mirrors neuro_core.index.Index so the calling conventions are identical.
    """

    def __init__(self, index_dir):
        self.db = lancedb.connect(str(index_dir))
        self.tbl = self.db.open_table(CARDS_TABLE)

    def _row_to_hit(self, row):
        return CardHit(
            id=row["id"],
            question_text=row.get("question_text", ""),
            answer_text=row.get("answer_text", ""),
            deck_name=row.get("deck_name", ""),
            deck_full=row.get("deck_full", ""),
            tags=row.get("tags", ""),
            model_name=row.get("model_name", ""),
            question_html=row.get("question_html", ""),
            answer_html=row.get("answer_html", ""),
            image_paths=list(row.get("image_paths") or []),
            text=row.get("text", ""),
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
