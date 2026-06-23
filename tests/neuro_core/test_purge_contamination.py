"""Hermetic tests for the contamination audit + guarded purge.

No network, no live index, no real PDF: a tiny synthetic LanceDB is built in ``tmp_path``
via the *production* table builders (real schema). Detection is INDEX-based — it reads the
chunks' ``chapter``/``page``/``text`` straight out of the table — so nothing is monkeypatched.

Fixture shape (mirrors the live Youmans case at a small scale):
  * ``CleanBook``  — all medical, no appended block.
  * ``DirtyBook``  — pages 1-20 medical, then an appended David-Icke-style book at pages
    21-40 (front matter "Copyright"/"Dedication"/"Contents" at 21-23, then >=15 chunks whose
    chapter is a distinctive Icke title + conspiracy text). Boundary = 21.
The SAFETY fixture interleaves a *medical* chunk inside the appended region → the purity
check fails → the book is EXCLUDED from the purge (never over-delete legit content).
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


def _chunk(book, page, chapter, text):
    return Chunk(id=f"{book}::p{page:04d}::0", book=book, chapter=chapter, page=page, text=text)


def _fig(book, page):
    # figure_path stem -> plate; build_visual_index makes id "<book>::<stem>".
    return {"book": book, "chapter": "C", "page": page,
            "figure_path": f"/assets/{book}/p{page:04d}.png",
            "caption": f"{book} fig {page}"}


# Distinctive appended-book chapter labels (curly quotes, like the real index) + conspiracy text.
_ICKE_CHAPTERS = [
    ("Chapter 2: Renegade perception", "renegade perception of the reptilian cult"),
    ("Chapter 3: The Pushbacker sting", "the pushbacker sting and the illuminati bloodline"),
    ("Chapter 11: Who controls the Cult?", "who controls the cult, asks david icke"),
    ("Chapter 12: Escaping Wetiko", "escaping wetiko and the annunaki control system"),
]


def _appended_block(book):
    """Pages 21-40: front matter (21-23) then >=15 Icke-style chunks (24-40)."""
    rows = [
        _chunk(book, 21, "Copyright", "first published in july 2021"),
        _chunk(book, 22, "Dedication", "dedicated to those who see"),
        _chunk(book, 23, "Contents", "table of contents of a renegade mind"),
    ]
    for page in range(24, 41):  # 17 chunks >= MIN_STRONG (15)
        chapter, text = _ICKE_CHAPTERS[page % len(_ICKE_CHAPTERS)]
        rows.append(_chunk(book, page, chapter, text))
    return rows


def _medical_dirty():
    return [_chunk("DirtyBook", p, f"{p} - Operative neurosurgery chapter",
                   f"medical operative technique discussion {p}") for p in range(1, 21)]


def _clean_book():
    titles = [
        "1 - Cerebral cortex cytoarchitecture and lamination",
        "2 - Ascending and descending spinal cord tracts",
        "3 - Cranial nerve nuclei of the brainstem",
        "4 - Vascular supply of the circle of willis",
        "5 - Posterior fossa and cerebellopontine angle",
    ]
    return [_chunk("CleanBook", i + 1, t, f"clean medical content {i + 1}")
            for i, t in enumerate(titles)]


def _build(d, chunks, figs, caps):
    build_index(chunks, _FakeEmbedder(), d)
    build_visual_index(figs, _FakeVisualEmbedder(), d)
    (d / "_gemini_captions.jsonl").write_text("\n".join(json.dumps(c) for c in caps) + "\n")


_CAPS = [
    {"id": "CleanBook::p0002", "caption": "clean fig 2", "model": "x"},
    {"id": "CleanBook::p0004", "caption": "clean fig 4", "model": "x"},
    {"id": "DirtyBook::p0005", "caption": "dirty medical fig 5", "model": "x"},
    {"id": "DirtyBook::p0025", "caption": "icke fig 25", "model": "x"},
    {"id": "DirtyBook::p0030", "caption": "icke fig 30", "model": "x"},
]
_FIGS = [_fig("CleanBook", 2), _fig("CleanBook", 4),
         _fig("DirtyBook", 5), _fig("DirtyBook", 25), _fig("DirtyBook", 30)]


@pytest.fixture
def index_dir(tmp_path):
    """Clean + Dirty(appended) — DirtyBook boundary should be 21, purity passes."""
    d = tmp_path / "idx"
    chunks = _clean_book() + _medical_dirty() + _appended_block("DirtyBook")
    _build(d, chunks, _FIGS, _CAPS)
    return d


@pytest.fixture
def index_dir_unsafe(tmp_path):
    """Same, but a MEDICAL chunk is interleaved at page 30 inside the appended region."""
    d = tmp_path / "idx"
    poison = _chunk("DirtyBook", 30, "30 - Microsurgical aneurysm clipping",
                    "legit operative neurosurgery content that must never be deleted")
    chunks = _clean_book() + _medical_dirty() + _appended_block("DirtyBook") + [poison]
    _build(d, chunks, _FIGS, _CAPS)
    return d


def _rows(db, table, *cols):
    at = db.open_table(table).to_arrow()
    return list(zip(*(at.column(c).to_pylist() for c in cols)))


def _df(db):
    at = db.open_table("chunks").to_arrow()
    return {c: at.column(c).to_pylist() for c in ("book", "page", "chapter", "text")}


def test_detect_is_index_based(index_dir):
    import pandas as pd
    db = lancedb.connect(str(index_dir))
    regions = pc.detect_contaminated_regions(pd.DataFrame(_df(db)))
    assert regions == {"DirtyBook": 21}      # first contaminated page; CleanBook absent


def test_gather_detects_only_contaminated_rows(index_dir):
    db = lancedb.connect(str(index_dir))
    per_book, aborted, marker_hits, total, deleted = pc.gather(db)

    assert per_book["DirtyBook"]["boundary"] == 21
    assert per_book["DirtyBook"]["chunks"] == 20      # pages 21-40 inclusive
    assert per_book["DirtyBook"]["figures"] == 2      # DirtyBook figs at p25, p30
    assert "CleanBook" not in per_book                # clean book not deletable
    assert aborted == {}
    assert total == 22
    assert deleted == {"DirtyBook::p0025", "DirtyBook::p0030"}
    # markers all fall inside the detected region (none reported out-of-region)
    assert all(not (b == "DirtyBook" and p >= 21) for b, p in marker_hits)


def test_audit_is_readonly_and_exits_nonzero(index_dir):
    before = sorted(_rows(lancedb.connect(str(index_dir)), "chunks", "book", "page"))
    rc = pc.main(["--index-dir", str(index_dir)])
    assert rc == 1                               # contamination found -> gate fails
    after = sorted(_rows(lancedb.connect(str(index_dir)), "chunks", "book", "page"))
    assert before == after                       # read-only: nothing mutated


def test_apply_purges_backs_up_and_is_idempotent(index_dir):
    rc = pc.main(["--apply", "--index-dir", str(index_dir)])
    assert rc == 0

    db = lancedb.connect(str(index_dir))
    chunk_rows = set(_rows(db, "chunks", "book", "page"))
    # contaminated DirtyBook pages gone
    assert not any(b == "DirtyBook" and p >= 21 for b, p in chunk_rows)
    # legit DirtyBook pages + every CleanBook page intact
    assert {("DirtyBook", 1), ("DirtyBook", 10), ("DirtyBook", 20)} <= chunk_rows
    assert sum(1 for b, _ in chunk_rows if b == "DirtyBook") == 20
    assert sum(1 for b, _ in chunk_rows if b == "CleanBook") == 5

    fig_rows = set(_rows(db, "figures", "book", "page"))
    assert not any(b == "DirtyBook" and p >= 21 for b, p in fig_rows)
    assert ("DirtyBook", 5) in fig_rows and ("CleanBook", 2) in fig_rows

    # captions for deleted figures dropped; others kept
    cap_ids = {json.loads(line)["id"]
               for line in (index_dir / "_gemini_captions.jsonl").read_text().splitlines()
               if line.strip()}
    assert cap_ids == {"CleanBook::p0002", "CleanBook::p0004", "DirtyBook::p0005"}

    # a backup was created first, with the whole tables + captions snapshot
    backups = list(index_dir.glob("_backup_purge_*"))
    assert len(backups) == 1
    assert (backups[0] / "chunks.lance").exists()
    assert (backups[0] / "figures.lance").exists()
    assert (backups[0] / "_gemini_captions.jsonl").exists()

    # idempotent: a second --apply is a clean no-op (no new backup), audit now exits 0
    rc2 = pc.main(["--apply", "--index-dir", str(index_dir)])
    assert rc2 == 0
    assert len(list(index_dir.glob("_backup_purge_*"))) == 1
    rc3 = pc.main(["--index-dir", str(index_dir)])
    assert rc3 == 0


def test_purity_check_excludes_impure_book_failsafe(index_dir_unsafe, capsys):
    """A medical chunk inside the appended region must ABORT that book (never over-delete)."""
    import pandas as pd
    db = lancedb.connect(str(index_dir_unsafe))

    # detection omits the impure book entirely
    regions = pc.detect_contaminated_regions(pd.DataFrame(_df(db)))
    assert regions == {}

    per_book, aborted, _mh, total, _ = pc.gather(db)
    assert per_book == {}
    assert "DirtyBook" in aborted
    assert aborted["DirtyBook"]["n_medical_in_region"] >= 1
    assert total == 0

    before = sorted(_rows(db, "chunks", "book", "page"))
    rc = pc.main(["--apply", "--index-dir", str(index_dir_unsafe)])
    assert rc == 1                               # flagged but unsafe -> non-zero
    out = capsys.readouterr().out.lower()
    assert "purity check failed" in out and "excluded" in out

    after = sorted(_rows(lancedb.connect(str(index_dir_unsafe)), "chunks", "book", "page"))
    assert before == after                       # fail-safe: nothing deleted
    assert not list(index_dir_unsafe.glob("_backup_purge_*"))  # no backup written


def test_filter_caption_lines_fails_safe():
    lines = [
        json.dumps({"id": "DirtyBook::p0025", "caption": "drop me"}),
        json.dumps({"id": "CleanBook::p0002", "caption": "keep me"}),
        "not-json-keep-this",
        json.dumps({"caption": "no id field keep"}),
        "",
    ]
    kept, dropped = pc._filter_caption_lines(lines, {"DirtyBook::p0025"})
    assert dropped == 1
    # the targeted line is gone; unparseable + id-less lines are KEPT (never over-delete)
    assert any("keep me" in k for k in kept)
    assert "not-json-keep-this" in kept
    assert any("no id field keep" in k for k in kept)
    assert all("drop me" not in k for k in kept)
