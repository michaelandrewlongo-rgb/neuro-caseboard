from collections import Counter

import numpy as np
import pytest

from neuro_core.visual_index import build_visual_index, VisualIndex


class FakeVisualEmbedder:
    def embed_images(self, paths):
        # deterministic 2-D vectors; content irrelevant for append bookkeeping
        return np.array([[1.0, 0.0]] * len(paths), dtype="float32")


def _figs(book, n=1, page=1):
    return [{"book": book, "chapter": "C", "page": page,
             "figure_path": f"/x/{book}/p{page:04d}_f{i:02d}.png",
             "caption": f"{book} figure {i}"} for i in range(n)]


@pytest.mark.integration
def test_visual_append_adds_new_book(tmp_path):
    emb = FakeVisualEmbedder()
    d = tmp_path / "idx"
    build_visual_index(_figs("BookA", 2) + _figs("BookB", 1), emb, d)
    assert VisualIndex(d).tbl.count_rows() == 3

    build_visual_index(_figs("BookC", 2), emb, d, mode="append")
    tbl = VisualIndex(d).tbl
    assert set(tbl.to_arrow().column("book").to_pylist()) == {"BookA", "BookB", "BookC"}
    assert tbl.count_rows() == 5


@pytest.mark.integration
def test_visual_append_is_idempotent(tmp_path):
    emb = FakeVisualEmbedder()
    d = tmp_path / "idx"
    build_visual_index(_figs("BookA", 1), emb, d)
    build_visual_index(_figs("BookC", 3), emb, d, mode="append")
    build_visual_index(_figs("BookC", 3), emb, d, mode="append")  # replace, no dup
    tbl = VisualIndex(d).tbl
    counts = Counter(tbl.to_arrow().column("book").to_pylist())
    assert counts["BookC"] == 3
    assert tbl.count_rows() == 4


@pytest.mark.integration
def test_visual_append_creates_table_when_absent(tmp_path):
    emb = FakeVisualEmbedder()
    d = tmp_path / "idx"
    build_visual_index(_figs("BookA", 2), emb, d, mode="append")
    assert VisualIndex(d).tbl.count_rows() == 2
