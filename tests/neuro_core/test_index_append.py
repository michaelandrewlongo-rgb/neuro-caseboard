from collections import Counter

import numpy as np
import pytest

from neuro_core.chunk import Chunk
from neuro_core.index import build_index, Index


class FakeEmbedder:
    def embed_texts(self, texts):
        return np.array([[1.0, 0.0] if "icp" in t.lower() else [0.0, 1.0]
                         for t in texts], dtype="float32")

    def embed_query(self, text):
        return np.array([1.0, 0.0] if "icp" in text.lower() else [0.0, 1.0],
                        dtype="float32")


def _chunks(book, text, page=1):
    return [Chunk(id=f"{book}::p{page}::0", book=book, chapter="C", page=page, text=text)]


@pytest.mark.integration
def test_append_adds_new_book_without_re_embedding_existing(tmp_path):
    emb = FakeEmbedder()
    d = tmp_path / "idx"
    build_index(_chunks("BookA", "alpha icp one") + _chunks("BookB", "beta spine two"), emb, d)
    assert Index(d).tbl.count_rows() == 2

    build_index(_chunks("BookC", "gamma icp three"), emb, d, mode="append")
    tbl = Index(d).tbl
    assert set(tbl.to_arrow().column("book").to_pylist()) == {"BookA", "BookB", "BookC"}
    assert tbl.count_rows() == 3


@pytest.mark.integration
def test_append_is_idempotent(tmp_path):
    emb = FakeEmbedder()
    d = tmp_path / "idx"
    build_index(_chunks("BookA", "alpha icp one"), emb, d)
    build_index(_chunks("BookC", "gamma icp three"), emb, d, mode="append")
    # re-append the same book -> replace its rows, never duplicate
    build_index(_chunks("BookC", "gamma icp three revised"), emb, d, mode="append")
    tbl = Index(d).tbl
    counts = Counter(tbl.to_arrow().column("book").to_pylist())
    assert counts["BookC"] == 1
    assert tbl.count_rows() == 2


@pytest.mark.integration
def test_append_creates_table_when_absent(tmp_path):
    emb = FakeEmbedder()
    d = tmp_path / "idx"
    build_index(_chunks("BookA", "alpha icp one"), emb, d, mode="append")
    assert Index(d).tbl.count_rows() == 1


@pytest.mark.integration
def test_append_fts_index_finds_new_book(tmp_path):
    emb = FakeEmbedder()
    d = tmp_path / "idx"
    build_index(_chunks("BookA", "alpha icp one"), emb, d)
    build_index(_chunks("BookC", "zzqx unique keyword three"), emb, d, mode="append")
    hits = Index(d).text_search("zzqx unique keyword", k=5)
    assert any(h.book == "BookC" for h in hits)
