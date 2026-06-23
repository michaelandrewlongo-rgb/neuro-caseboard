"""Hermetic tests for the contamination audit + guarded purge.

No network, no live index, no real PDF: a tiny synthetic LanceDB is built in ``tmp_path``
via the *production* table builders (real schema), and ``detect_content_ends`` is
monkeypatched so book->content_end detection needs no PDF.
"""
import json

import lancedb
import numpy as np
import pytest

from neuro_core.chunk import Chunk
from neuro_core.index import build_index
from neuro_core.visual_index import build_visual_index
from neuro_core.scripts import purge_contamination as pc


class _FakeEmbedder:
    def embed_texts(self, texts):
        return np.array([[1.0, 0.0]] * len(texts), dtype="float32")


class _FakeVisualEmbedder:
    def embed_images(self, paths):
        return np.array([[1.0, 0.0]] * len(paths), dtype="float32")


def _chunk(book, page, text):
    return Chunk(id=f"{book}::p{page}::0", book=book, chapter="C", page=page, text=text)


def _fig(book, page):
    # figure_path stem -> plate; build_visual_index makes id "<book>::<stem>".
    return {"book": book, "chapter": "C", "page": page,
            "figure_path": f"/assets/{book}/p{page:04d}.png",
            "caption": f"{book} fig {page}"}


# DirtyBook: pages 1-3 medical, pages 10-12 conspiracy markers; content_end = 10.
CONTENT_ENDS = {"DirtyBook": 10, "CleanBook": None}


@pytest.fixture
def index_dir(tmp_path):
    d = tmp_path / "idx"
    chunks = [
        _chunk("CleanBook", 1, "cerebral cortex cytoarchitecture and lamination"),
        _chunk("CleanBook", 2, "ascending and descending spinal cord tracts"),
        _chunk("CleanBook", 3, "cranial nerve nuclei of the brainstem"),
        _chunk("CleanBook", 4, "vascular supply of the circle of willis"),
        _chunk("CleanBook", 5, "posterior fossa and cerebellopontine angle"),
        _chunk("DirtyBook", 1, "glioma resection with awake mapping"),
        _chunk("DirtyBook", 2, "anterior communicating artery aneurysm clipping"),
        _chunk("DirtyBook", 3, "skull base foramina and their contents"),
        _chunk("DirtyBook", 10, "the reptilian brain serves the david icke cult"),
        _chunk("DirtyBook", 11, "illuminati annunaki bloodlines and the rothschild banking"),
        _chunk("DirtyBook", 12, "perceptions of a renegade mind and the freemason agenda"),
    ]
    build_index(chunks, _FakeEmbedder(), d)
    figs = [
        _fig("CleanBook", 2), _fig("CleanBook", 4),
        _fig("DirtyBook", 1),
        _fig("DirtyBook", 10), _fig("DirtyBook", 11), _fig("DirtyBook", 12),
    ]
    build_visual_index(figs, _FakeVisualEmbedder(), d)
    caps = [
        {"id": "CleanBook::p0002", "caption": "clean fig 2", "model": "x"},
        {"id": "CleanBook::p0004", "caption": "clean fig 4", "model": "x"},
        {"id": "DirtyBook::p0001", "caption": "dirty medical fig 1", "model": "x"},
        {"id": "DirtyBook::p0010", "caption": "icke fig 10", "model": "x"},
        {"id": "DirtyBook::p0011", "caption": "icke fig 11", "model": "x"},
        {"id": "DirtyBook::p0012", "caption": "icke fig 12", "model": "x"},
    ]
    (d / "_gemini_captions.jsonl").write_text(
        "\n".join(json.dumps(c) for c in caps) + "\n")
    return d


def _rows(db, table, *cols):
    at = db.open_table(table).to_arrow()
    return list(zip(*(at.column(c).to_pylist() for c in cols)))


def test_gather_detects_only_contaminated_rows(index_dir):
    db = lancedb.connect(str(index_dir))
    per_book, marker_hits, total, deleted = pc.gather(db, CONTENT_ENDS)

    assert per_book["DirtyBook"] == {"content_end": 10, "chunks": 3, "figures": 3}
    assert "CleanBook" not in per_book          # clean book (content_end None) not deletable
    assert total == 6
    assert marker_hits == []                     # all markers fall inside the boundary
    assert deleted == {"DirtyBook::p0010", "DirtyBook::p0011", "DirtyBook::p0012"}


def test_audit_is_readonly_and_exits_nonzero(index_dir, monkeypatch):
    monkeypatch.setattr(pc, "detect_content_ends", lambda corpus_dir: CONTENT_ENDS)
    before = sorted(_rows(lancedb.connect(str(index_dir)), "chunks", "book", "page"))
    rc = pc.main(["--index-dir", str(index_dir), "--corpus-dir", "ignored"])
    assert rc == 1                               # contamination found -> gate fails
    after = sorted(_rows(lancedb.connect(str(index_dir)), "chunks", "book", "page"))
    assert before == after                       # read-only: nothing mutated


def test_apply_purges_backs_up_and_is_idempotent(index_dir, monkeypatch):
    monkeypatch.setattr(pc, "detect_content_ends", lambda corpus_dir: CONTENT_ENDS)

    rc = pc.main(["--apply", "--index-dir", str(index_dir), "--corpus-dir", "ignored"])
    assert rc == 0

    db = lancedb.connect(str(index_dir))
    chunk_rows = set(_rows(db, "chunks", "book", "page"))
    # contaminated DirtyBook pages gone
    assert not any(b == "DirtyBook" and p >= 10 for b, p in chunk_rows)
    # legit DirtyBook pages + every CleanBook page intact
    assert {("DirtyBook", 1), ("DirtyBook", 2), ("DirtyBook", 3)} <= chunk_rows
    assert sum(1 for b, _ in chunk_rows if b == "CleanBook") == 5

    fig_rows = set(_rows(db, "figures", "book", "page"))
    assert not any(b == "DirtyBook" and p >= 10 for b, p in fig_rows)
    assert ("DirtyBook", 1) in fig_rows and ("CleanBook", 2) in fig_rows

    # captions for deleted figures dropped; others kept
    cap_ids = {json.loads(line)["id"]
               for line in (index_dir / "_gemini_captions.jsonl").read_text().splitlines()
               if line.strip()}
    assert cap_ids == {"CleanBook::p0002", "CleanBook::p0004", "DirtyBook::p0001"}

    # a backup was created first, with the whole tables + captions snapshot
    backups = list(index_dir.glob("_backup_purge_*"))
    assert len(backups) == 1
    assert (backups[0] / "chunks.lance").exists()
    assert (backups[0] / "figures.lance").exists()
    assert (backups[0] / "_gemini_captions.jsonl").exists()

    # idempotent: a second --apply is a clean no-op (no new backup), audit now exits 0
    rc2 = pc.main(["--apply", "--index-dir", str(index_dir), "--corpus-dir", "ignored"])
    assert rc2 == 0
    assert len(list(index_dir.glob("_backup_purge_*"))) == 1
    rc3 = pc.main(["--index-dir", str(index_dir), "--corpus-dir", "ignored"])
    assert rc3 == 0


def test_filter_caption_lines_fails_safe(index_dir):
    lines = [
        json.dumps({"id": "DirtyBook::p0010", "caption": "drop me"}),
        json.dumps({"id": "CleanBook::p0002", "caption": "keep me"}),
        "not-json-keep-this",
        json.dumps({"caption": "no id field keep"}),
        "",
    ]
    kept, dropped = pc._filter_caption_lines(lines, {"DirtyBook::p0010"})
    assert dropped == 1
    # the targeted line is gone; unparseable + id-less lines are KEPT (never over-delete)
    assert any("keep me" in k for k in kept)
    assert "not-json-keep-this" in kept
    assert any("no id field keep" in k for k in kept)
    assert all("drop me" not in k for k in kept)
