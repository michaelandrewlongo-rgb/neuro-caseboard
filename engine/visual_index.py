import lancedb

from .index import Hit

FIGURES_TABLE = "figures"


def build_visual_index(figure_pages, embedder, index_dir, batch_size=64,
                       on_progress=None):
    """figure_pages: list of dicts with keys book, chapter, page, figure_path,
    caption. Embeds each figure_path PNG and writes the `figures` LanceDB table."""
    db = lancedb.connect(str(index_dir))
    paths = [fp["figure_path"] for fp in figure_pages]
    vectors = []
    for i in range(0, len(paths), batch_size):
        vectors.extend(embedder.embed_images(paths[i:i + batch_size]))
        if on_progress:
            on_progress(min(i + batch_size, len(paths)), len(paths))
    rows = []
    for fp, v in zip(figure_pages, vectors):
        rows.append({
            "id": f"{fp['book']}::p{fp['page']}",
            "book": fp["book"],
            "chapter": fp.get("chapter") or "",
            "page": int(fp["page"]),
            "figure_path": fp["figure_path"],
            "caption": fp.get("caption") or "",
            "vector": [float(x) for x in v],
        })
    return db.create_table(FIGURES_TABLE, data=rows, mode="overwrite")


class VisualIndex:
    def __init__(self, index_dir):
        self.db = lancedb.connect(str(index_dir))
        self.tbl = self.db.open_table(FIGURES_TABLE)

    def image_search(self, query_vector, k):
        # Default L2 metric gives the same rank order as cosine here because the
        # vectors are L2-normalized at embed time (VisualEmbedder), and the caller
        # fuses by rank, not score.
        rows = (self.tbl.search([float(x) for x in query_vector])
                .limit(k).to_list())
        return [
            Hit(id=r["id"], book=r["book"], chapter=r["chapter"] or None,
                page=int(r["page"]), text=r["caption"] or "",
                has_figure=True, caption=(r["caption"] or None),
                figure_path=r["figure_path"])
            for r in rows
        ]
