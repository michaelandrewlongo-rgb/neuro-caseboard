# Engine Readiness (Profiles + Resumable Indexing) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the engine run well on GPU-less laptops (hardware profiles, Apple-Silicon support) and make indexing per-book resumable with a recorded embed model, per the resident-packaging spec (`docs/superpowers/specs/2026-06-09-resident-packaging-design.md`).

**Architecture:** A new `books` LanceDB catalog table records each indexed book's file hash + embed model; `scripts/build_index.py` becomes an incremental skip/new/changed loop over that catalog (with `--rebuild` for the old full overwrite). A small `engine/profiles.py` maps detected hardware to model presets; `resolve_device("auto")` learns MPS. `get_engine` refuses to query an index built with a different embedder.

**Tech Stack:** Python 3.12, LanceDB, sentence-transformers, PyMuPDF (fitz), pytest (existing `integration` marker convention).

**This is Plan A of four.** Plan B (resident CLI + setup wizard), Plan C (MCP server), Plan D (public repo export + installer + CI) follow once this lands. Everything here is useful to the current private setup on its own.

**Branch:** create `engine-readiness` off `master`. Note: PR #1 (Marker) defines similarly-named index helpers on its own branch — this plan does NOT depend on it; expect a manual reconcile if/when PR #1 lands.

**Conventions:** interpreter is `python3`. Tests touching real LanceDB get `@pytest.mark.integration` (run all: `python3 -m pytest -q`; unit only: `-m "not integration"`).

---

### Task 1: MPS support in `resolve_device`

**Files:**
- Modify: `engine/config.py:36-44`
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
import sys

from engine.config import resolve_device


class _Avail:
    def __init__(self, avail):
        self._avail = avail

    def is_available(self):
        return self._avail


class _FakeBackends:
    def __init__(self, mps_avail):
        self.mps = _Avail(mps_avail)


class _FakeTorch:
    def __init__(self, cuda=False, mps=False):
        self.cuda = _Avail(cuda)
        self.backends = _FakeBackends(mps)


def test_resolve_device_auto_prefers_cuda_over_mps(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(cuda=True, mps=True))
    assert resolve_device("auto") == "cuda"


def test_resolve_device_auto_falls_back_to_mps(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(cuda=False, mps=True))
    assert resolve_device("auto") == "mps"


def test_resolve_device_auto_cpu_when_no_accelerator(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(cuda=False, mps=False))
    assert resolve_device("auto") == "cpu"
```

(If `tests/test_config.py` already imports `resolve_device` or `sys`, don't duplicate the import.)

- [ ] **Step 2: Run tests to verify the MPS one fails**

Run: `python3 -m pytest tests/test_config.py -v -k resolve_device`
Expected: `test_resolve_device_auto_falls_back_to_mps` FAILS (returns `"cpu"`); the other two pass.

- [ ] **Step 3: Implement**

In `engine/config.py`, replace the body of `resolve_device`:

```python
def resolve_device(device):
    """Resolve 'auto' to 'cuda', then 'mps' (Apple Silicon), else 'cpu'.
    Pass other values through."""
    if device != "auto":
        return device
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
        return "cpu"
    except Exception:
        return "cpu"
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/config.py tests/test_config.py
git commit -m "feat: resolve_device auto-detects Apple-Silicon MPS"
```

---

### Task 2: Hardware profiles module

**Files:**
- Create: `engine/profiles.py`
- Test: `tests/test_profiles.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_profiles.py`:

```python
import sys

from engine.profiles import PROFILES, detect_profile
from tests.test_config import _FakeTorch


def test_profiles_have_models_for_both_tiers():
    for name in ("gpu", "cpu"):
        assert "EMBED_MODEL" in PROFILES[name]
        assert "RERANK_MODEL" in PROFILES[name]
    # the gpu profile is the current production stack
    assert PROFILES["gpu"]["EMBED_MODEL"] == "BAAI/bge-large-en-v1.5"
    assert PROFILES["gpu"]["RERANK_MODEL"] == "BAAI/bge-reranker-v2-m3"
    # the cpu profile is small/fast
    assert PROFILES["cpu"]["EMBED_MODEL"] == "BAAI/bge-small-en-v1.5"
    assert PROFILES["cpu"]["RERANK_MODEL"] == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_detect_profile_gpu_on_cuda(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(cuda=True))
    assert detect_profile() == "gpu"


def test_detect_profile_gpu_on_mps(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(mps=True))
    assert detect_profile() == "gpu"


def test_detect_profile_cpu_otherwise(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())
    assert detect_profile() == "cpu"
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.profiles'`.

- [ ] **Step 3: Implement**

Create `engine/profiles.py`:

```python
"""Hardware profiles: retrieval-model presets keyed by detected accelerator.

The setup wizard (Plan B) writes the chosen profile's models into the user's
config; the engine itself only ever sees EMBED_MODEL / RERANK_MODEL keys.
"""
from .config import resolve_device

PROFILES = {
    # Current production stack — needs CUDA or Apple-Silicon MPS to be usable
    # interactively (the 568M reranker takes minutes per query on plain CPU).
    "gpu": {
        "EMBED_MODEL": "BAAI/bge-large-en-v1.5",
        "RERANK_MODEL": "BAAI/bge-reranker-v2-m3",
    },
    # Plain-CPU laptops: small embedder + tiny cross-encoder, seconds per query.
    "cpu": {
        "EMBED_MODEL": "BAAI/bge-small-en-v1.5",
        "RERANK_MODEL": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    },
}


def detect_profile():
    """'gpu' when CUDA or MPS is available, else 'cpu'."""
    return "gpu" if resolve_device("auto") in ("cuda", "mps") else "cpu"
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_profiles.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/profiles.py tests/test_profiles.py
git commit -m "feat: hardware profiles (gpu/cpu model presets + detection)"
```

---

### Task 3: Book catalog (`engine/catalog.py`)

**Files:**
- Create: `engine/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_catalog.py`:

```python
import pytest

from engine.catalog import (sha256_file, read_catalog, upsert_book,
                            delete_book_entry, catalog_embed_model)


def test_sha256_file_changes_with_content(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"hello")
    h1 = sha256_file(f)
    f.write_bytes(b"hello world")
    h2 = sha256_file(f)
    assert h1 != h2
    assert len(h1) == 64


@pytest.mark.integration
def test_catalog_roundtrip(tmp_path):
    idx = tmp_path / "index"
    assert read_catalog(idx) == {}                      # no table yet
    assert catalog_embed_model(idx) is None

    upsert_book(idx, "BookA", "hashA", "model-x", 10)
    upsert_book(idx, "BookB", "hashB", "model-x", 20)
    cat = read_catalog(idx)
    assert set(cat) == {"BookA", "BookB"}
    assert cat["BookA"]["file_hash"] == "hashA"
    assert cat["BookB"]["chunk_count"] == 20
    assert catalog_embed_model(idx) == "model-x"

    upsert_book(idx, "BookA", "hashA2", "model-x", 11)  # replaces, no dup
    cat = read_catalog(idx)
    assert len(cat) == 2
    assert cat["BookA"]["file_hash"] == "hashA2"

    delete_book_entry(idx, "BookB")
    assert set(read_catalog(idx)) == {"BookA"}


@pytest.mark.integration
def test_catalog_embed_model_mixed_raises(tmp_path):
    idx = tmp_path / "index"
    upsert_book(idx, "BookA", "h1", "model-x", 1)
    upsert_book(idx, "BookB", "h2", "model-y", 1)
    with pytest.raises(ValueError):
        catalog_embed_model(idx)


@pytest.mark.integration
def test_catalog_quotes_book_names(tmp_path):
    idx = tmp_path / "index"
    upsert_book(idx, "O'Brien's Atlas", "h1", "m", 1)
    upsert_book(idx, "O'Brien's Atlas", "h2", "m", 2)   # upsert, not crash
    assert read_catalog(idx)["O'Brien's Atlas"]["file_hash"] == "h2"
    delete_book_entry(idx, "O'Brien's Atlas")
    assert read_catalog(idx) == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.catalog'`.

- [ ] **Step 3: Implement**

Create `engine/catalog.py`:

```python
"""Book catalog: which PDFs are in the index, keyed by content hash.

One row per indexed book in a `books` LanceDB table (alongside `chunks`):
    book (pdf stem) | file_hash (sha256) | embed_model | chunk_count
This is the contract for incremental indexing: a book is skipped when its
hash AND the configured embed model both match its catalog row.
"""
import hashlib

import lancedb

BOOKS_TABLE = "books"


class IndexMismatchError(RuntimeError):
    """The index was built with a different embed model than configured."""


def sha256_file(path, block_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def _quote(value):
    return value.replace("'", "''")


def read_catalog(index_dir):
    """{book: {book, file_hash, embed_model, chunk_count}} ({} if no table)."""
    db = lancedb.connect(str(index_dir))
    if BOOKS_TABLE not in db.table_names():
        return {}
    rows = db.open_table(BOOKS_TABLE).to_arrow().to_pylist()
    return {r["book"]: r for r in rows}


def upsert_book(index_dir, book, file_hash, embed_model, chunk_count):
    db = lancedb.connect(str(index_dir))
    row = {"book": book, "file_hash": file_hash,
           "embed_model": embed_model, "chunk_count": int(chunk_count)}
    if BOOKS_TABLE not in db.table_names():
        db.create_table(BOOKS_TABLE, data=[row])
        return
    tbl = db.open_table(BOOKS_TABLE)
    tbl.delete(f"book = '{_quote(book)}'")
    tbl.add([row])


def delete_book_entry(index_dir, book):
    db = lancedb.connect(str(index_dir))
    if BOOKS_TABLE in db.table_names():
        db.open_table(BOOKS_TABLE).delete(f"book = '{_quote(book)}'")


def catalog_embed_model(index_dir):
    """The single embed model recorded in the catalog; None when no catalog
    exists (pre-catalog index — treated as compatible for backward
    compatibility). Raises ValueError on mixed models (corrupt catalog)."""
    models = {r["embed_model"] for r in read_catalog(index_dir).values()}
    if not models:
        return None
    if len(models) > 1:
        raise ValueError(f"catalog has mixed embed models: {sorted(models)}")
    return models.pop()
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_catalog.py -v`
Expected: all PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/catalog.py tests/test_catalog.py
git commit -m "feat: book catalog table (file hash + embed model per book)"
```

---

### Task 4: Per-book chunk operations in `engine/index.py`

**Files:**
- Modify: `engine/index.py` (refactor `build_index` to share `_chunk_to_row`; add `append_chunks`, `delete_book`, `rebuild_fts`, `table_exists`)
- Test: `tests/test_index.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_index.py` (it already defines `FakeEmbedder` and imports `Chunk`; reuse them):

```python
from engine.index import append_chunks, delete_book, rebuild_fts, table_exists


def _chunk(book, page, idx, text):
    return Chunk(id=f"{book}::p{page}::{idx}", book=book, chapter=None,
                 page=page, text=text)


@pytest.mark.integration
def test_append_creates_then_extends_table(tmp_path):
    idx = tmp_path / "index"
    emb = FakeEmbedder()
    assert not table_exists(idx)

    append_chunks([_chunk("BookA", 1, 0, "icp")], emb, idx)
    assert table_exists(idx)
    rebuild_fts(idx)
    store = Index(idx)
    assert len(store.text_search("icp", 5)) == 1

    append_chunks([_chunk("BookB", 1, 0, "spine")], emb, idx)
    rebuild_fts(idx)
    store = Index(idx)
    assert {h.book for h in store.vector_search(emb.embed_texts(["icp"])[0], 5)} \
        == {"BookA", "BookB"}


@pytest.mark.integration
def test_delete_book_removes_only_that_book(tmp_path):
    idx = tmp_path / "index"
    emb = FakeEmbedder()
    append_chunks([_chunk("BookA", 1, 0, "icp"),
                   _chunk("BookB", 1, 0, "spine")], emb, idx)
    delete_book(idx, "BookA")
    rebuild_fts(idx)
    store = Index(idx)
    hits = store.vector_search(emb.embed_texts(["spine"])[0], 5)
    assert {h.book for h in hits} == {"BookB"}
```

If `FakeEmbedder.embed_texts` only knows fixed words, extend its table so both
`"icp"` and `"spine"` resolve (check the existing class first — it already maps
those two words; if a queried word is missing, add it to the table rather than
changing behavior for existing tests).

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_index.py -v -k "append or delete_book"`
Expected: FAIL with `ImportError: cannot import name 'append_chunks'`.

- [ ] **Step 3: Implement**

In `engine/index.py`, extract the row builder and add the helpers (keep
`build_index` behavior identical — it now calls `_chunk_to_row`):

```python
def _chunk_to_row(c, v):
    return {
        "id": c.id,
        "book": c.book,
        "chapter": c.chapter or "",
        "page": int(c.page),
        "text": c.text,
        "vector": [float(x) for x in v],
        "has_figure": bool(c.has_figure),
        "caption": c.caption or "",
        "figure_path": c.figure_path or "",
    }


def _embed_all(chunks, embedder, batch_size, on_progress):
    texts = [c.text for c in chunks]
    vectors = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(embedder.embed_texts(texts[i:i + batch_size]))
        if on_progress:
            on_progress(min(i + batch_size, len(texts)), len(texts))
    return vectors


def build_index(chunks, embedder, index_dir, batch_size=256, on_progress=None):
    db = lancedb.connect(str(index_dir))
    vectors = _embed_all(chunks, embedder, batch_size, on_progress)
    rows = [_chunk_to_row(c, v) for c, v in zip(chunks, vectors)]
    tbl = db.create_table(TABLE, data=rows, mode="overwrite")
    tbl.create_fts_index("text", replace=True)
    return tbl


def table_exists(index_dir, name=TABLE):
    return name in lancedb.connect(str(index_dir)).table_names()


def append_chunks(chunks, embedder, index_dir, batch_size=256, on_progress=None):
    """Embed and append; creates the chunks table when absent.
    Caller is responsible for rebuild_fts() after the last append."""
    db = lancedb.connect(str(index_dir))
    vectors = _embed_all(chunks, embedder, batch_size, on_progress)
    rows = [_chunk_to_row(c, v) for c, v in zip(chunks, vectors)]
    if TABLE in db.table_names():
        db.open_table(TABLE).add(rows)
    else:
        db.create_table(TABLE, data=rows)


def delete_book(index_dir, book):
    db = lancedb.connect(str(index_dir))
    if TABLE in db.table_names():
        db.open_table(TABLE).delete("book = '{}'".format(book.replace("'", "''")))


def rebuild_fts(index_dir):
    db = lancedb.connect(str(index_dir))
    db.open_table(TABLE).create_fts_index("text", replace=True)
```

- [ ] **Step 4: Run the whole index test file**

Run: `python3 -m pytest tests/test_index.py -v`
Expected: all PASS (old tests prove the `build_index` refactor changed nothing).

- [ ] **Step 5: Commit**

```bash
git add engine/index.py tests/test_index.py
git commit -m "feat: per-book index ops (append_chunks, delete_book, rebuild_fts)"
```

---

### Task 5: Embed-model mismatch guard at query time

**Files:**
- Modify: `engine/query.py:140-161` (`get_engine`)
- Modify: `cli/ask.py` (catch the new error)
- Test: `tests/test_query.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_query.py`:

```python
import pytest

from engine.catalog import IndexMismatchError, upsert_book


@pytest.mark.integration
def test_get_engine_rejects_mismatched_embed_model(tmp_path, monkeypatch):
    import engine.query as q
    from engine.config import load_config

    monkeypatch.setattr(q, "_engine", None)
    upsert_book(tmp_path, "BookA", "h", "BAAI/bge-large-en-v1.5", 1)

    monkeypatch.setenv("INDEX_DIR", str(tmp_path))
    monkeypatch.setenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    cfg = load_config(env_file="/nonexistent")

    with pytest.raises(IndexMismatchError) as e:
        q.get_engine(cfg)
    assert "--rebuild" in str(e.value)
    monkeypatch.setattr(q, "_engine", None)   # don't poison the cached engine
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_query.py -v -k mismatch`
Expected: FAIL — `get_engine` raises a LanceDB "table chunks not found" error (or
succeeds in raising nothing before that), NOT `IndexMismatchError`.

- [ ] **Step 3: Implement**

In `engine/query.py`, add to the imports:

```python
from .catalog import catalog_embed_model, IndexMismatchError
```

In `get_engine`, immediately after `config = config or load_config()`:

```python
    built_with = catalog_embed_model(config.index_dir)
    if built_with is not None and built_with != config.embed_model:
        raise IndexMismatchError(
            f"This index was built with embed model '{built_with}' but the "
            f"current config requests '{config.embed_model}'. Rebuild it: "
            f"python3 -m scripts.build_index --rebuild")
```

(`None` = pre-catalog index → allowed, so the existing personal index keeps
working untouched.)

In `cli/ask.py`, mirror the `GpuNotReadyError` handling:

```python
from engine.catalog import IndexMismatchError
```

and extend the try/except:

```python
    try:
        result = query(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        sys.exit(1)
    except IndexMismatchError as e:
        print(f"Index mismatch: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_query.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/query.py cli/ask.py tests/test_query.py
git commit -m "feat: refuse to query an index built with a different embedder"
```

---

### Task 6: Incremental `scripts/build_index.py`

**Files:**
- Rewrite: `scripts/build_index.py`
- Test: `tests/test_build_index.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_index.py`:

```python
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.build_index import plan_books, run
from engine.catalog import read_catalog, upsert_book


def make_pdf(path, text):
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


class CountingEmbedder:
    """Deterministic 2-D embedder that counts how many texts it embeds."""
    def __init__(self):
        self.embedded = 0

    def embed_texts(self, texts):
        self.embedded += len(texts)
        return np.asarray([[1.0, 0.0]] * len(texts), dtype="float32")

    def embed_query(self, text):
        return np.asarray([1.0, 0.0], dtype="float32")


def make_cfg(tmp_path):
    return SimpleNamespace(
        corpus_dir=tmp_path / "corpus",
        index_dir=tmp_path / "index",
        assets_dir=tmp_path / "assets",
        figure_dpi=72,
        figure_area_threshold=0.1,
        chunk_max_words=600,
        chunk_overlap_words=80,
        embed_model="fake-model",
        embed_device="cpu",
        visual_retrieval=False,
        visual_model="",
    )


def test_plan_books_classifies(tmp_path):
    a = tmp_path / "BookA.pdf"
    b = tmp_path / "BookB.pdf"
    a.write_bytes(b"aaa")
    b.write_bytes(b"bbb")
    from engine.catalog import sha256_file
    cat = {"BookA": {"book": "BookA", "file_hash": sha256_file(a),
                     "embed_model": "fake-model", "chunk_count": 1}}
    plan = plan_books([a, b], cat, "fake-model")
    assert [(p[1], p[3]) for p in plan] == [("BookA", "skip"), ("BookB", "new")]

    a.write_bytes(b"changed")
    plan = plan_books([a], cat, "fake-model")
    assert plan[0][3] == "changed"

    plan = plan_books([a], cat, "other-model")   # model change != hash match
    assert plan[0][3] == "changed"


@pytest.mark.integration
def test_run_is_incremental(tmp_path, capsys):
    cfg = make_cfg(tmp_path)
    cfg.corpus_dir.mkdir()
    make_pdf(cfg.corpus_dir / "BookA.pdf", "intracranial pressure is discussed")
    make_pdf(cfg.corpus_dir / "BookB.pdf", "the lumbar spine is discussed")

    emb = CountingEmbedder()
    run(cfg, embedder=emb)                       # first run: both books
    first = emb.embedded
    assert first > 0
    assert set(read_catalog(cfg.index_dir)) == {"BookA", "BookB"}

    run(cfg, embedder=emb)                       # second run: all skip
    assert emb.embedded == first

    make_pdf(cfg.corpus_dir / "BookB.pdf", "the cervical spine is discussed")
    run(cfg, embedder=emb)                       # only BookB re-embeds
    assert 0 < emb.embedded - first < first


@pytest.mark.integration
def test_run_removes_books_deleted_from_corpus(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.corpus_dir.mkdir()
    make_pdf(cfg.corpus_dir / "BookA.pdf", "alpha text")
    make_pdf(cfg.corpus_dir / "BookB.pdf", "beta text")
    run(cfg, embedder=CountingEmbedder())

    (cfg.corpus_dir / "BookB.pdf").unlink()
    run(cfg, embedder=CountingEmbedder())
    assert set(read_catalog(cfg.index_dir)) == {"BookA"}


@pytest.mark.integration
def test_run_aborts_on_embed_model_mismatch_without_rebuild(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.corpus_dir.mkdir()
    make_pdf(cfg.corpus_dir / "BookA.pdf", "alpha text")
    upsert_book(cfg.index_dir, "Old", "h", "other-model", 1)
    with pytest.raises(SystemExit):
        run(cfg, embedder=CountingEmbedder())


@pytest.mark.integration
def test_run_rebuild_overwrites_everything(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.corpus_dir.mkdir()
    make_pdf(cfg.corpus_dir / "BookA.pdf", "alpha text")
    upsert_book(cfg.index_dir, "Stale", "h", "other-model", 1)
    run(cfg, embedder=CountingEmbedder(), rebuild=True)
    assert set(read_catalog(cfg.index_dir)) == {"BookA"}
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_build_index.py -v`
Expected: FAIL with `ImportError: cannot import name 'plan_books'`.

- [ ] **Step 3: Rewrite `scripts/build_index.py`**

```python
import argparse
import sys
import time
from pathlib import Path

from engine import catalog
from engine.config import load_config, resolve_device
from engine.ingest import extract_pages, coverage_from_records
from engine.chunk import chunk_pages
from engine.embed import Embedder
from engine.index import (append_chunks, build_index, delete_book,
                          rebuild_fts, table_exists)


def plan_books(pdfs, cat, embed_model):
    """Classify each pdf against the catalog.
    Returns [(pdf_path, book, file_hash, action)] with action in
    'skip' | 'new' | 'changed'."""
    plan = []
    for pdf in pdfs:
        book = pdf.stem
        h = catalog.sha256_file(pdf)
        entry = cat.get(book)
        if entry is None:
            action = "new"
        elif entry["file_hash"] == h and entry["embed_model"] == embed_model:
            action = "skip"
        else:
            action = "changed"
        plan.append((pdf, book, h, action))
    return plan


def _extract_book(pdf, cfg):
    records = extract_pages(pdf, render=True, assets_dir=cfg.assets_dir,
                            dpi=cfg.figure_dpi,
                            area_threshold=cfg.figure_area_threshold)
    chunks = chunk_pages(records, cfg.chunk_max_words, cfg.chunk_overlap_words)
    return records, chunks


def _visual_available():
    try:
        import open_clip  # noqa: F401
        return True
    except ImportError:
        return False


def _build_visual(records, cfg, device):
    from engine.visual_embed import VisualEmbedder
    from engine.visual_index import build_visual_index
    fig_pages = {}
    for r in records:
        if r.has_figure and r.figure_path and r.figure_path not in fig_pages:
            fig_pages[r.figure_path] = {
                "book": r.book, "chapter": r.chapter, "page": r.page,
                "figure_path": r.figure_path, "caption": r.caption}
    fig_pages = list(fig_pages.values())
    print(f"\nBuilding visual index ({len(fig_pages)} figure pages) "
          f"with '{cfg.visual_model}' ...", flush=True)
    vemb = VisualEmbedder(cfg.visual_model, device=device)
    build_visual_index(fig_pages, vemb, cfg.index_dir)
    print("Visual index built.")


def run(cfg, rebuild=False, embedder=None):
    pdfs = sorted(Path(cfg.corpus_dir).glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {cfg.corpus_dir}\n")
    device = resolve_device(cfg.embed_device)
    if embedder is None:
        print(f"Loading embedding model '{cfg.embed_model}' on device "
              f"'{device}' (requested '{cfg.embed_device}') ...", flush=True)
        embedder = Embedder(cfg.embed_model, device=device)

    def progress(done, total):
        print(f"    embedded {done}/{total} chunks", flush=True)

    if rebuild:
        records, chunks = [], []
        t0 = time.time()
        for i, pdf in enumerate(pdfs, 1):
            print(f"  [{i}/{len(pdfs)}] reading {pdf.name} ...", flush=True)
            recs, cks = _extract_book(pdf, cfg)
            records.extend(recs)
            chunks.extend(cks)
            print(f"        {len(recs)} pages "
                  f"({time.time() - t0:.0f}s elapsed)", flush=True)
        _print_coverage(records)
        print(f"\nTotal pages: {len(records)} | total chunks: {len(chunks)}")
        build_index(chunks, embedder, cfg.index_dir, on_progress=progress)
        for pdf, book, h, _ in plan_books(pdfs, {}, cfg.embed_model):
            n = sum(1 for c in chunks if c.book == book)
            catalog.upsert_book(cfg.index_dir, book, h, cfg.embed_model, n)
        for stale in set(catalog.read_catalog(cfg.index_dir)) - \
                {p.stem for p in pdfs}:
            catalog.delete_book_entry(cfg.index_dir, stale)
        print(f"\nIndex rebuilt at {cfg.index_dir}")
        if cfg.visual_retrieval and _visual_available():
            _build_visual(records, cfg, device)
        elif cfg.visual_retrieval:
            print("\nNote: open_clip not installed — visual lane skipped "
                  "(install the [visual] extra to enable it).")
        return

    # Incremental path
    built_with = catalog.catalog_embed_model(cfg.index_dir)
    if built_with is not None and built_with != cfg.embed_model:
        sys.exit(f"This index was built with embed model '{built_with}' but "
                 f"the config requests '{cfg.embed_model}'. Run with "
                 f"--rebuild to re-embed everything.")

    cat = catalog.read_catalog(cfg.index_dir)
    plan = plan_books(pdfs, cat, cfg.embed_model)
    changed_any = False

    for stale in set(cat) - {book for _, book, _, _ in plan}:
        print(f"  removing '{stale}' (PDF no longer in corpus)")
        delete_book(cfg.index_dir, stale)
        catalog.delete_book_entry(cfg.index_dir, stale)
        changed_any = True

    for i, (pdf, book, h, action) in enumerate(plan, 1):
        if action == "skip":
            print(f"  [{i}/{len(plan)}] {book}: up to date, skipping")
            continue
        print(f"  [{i}/{len(plan)}] {book}: {action} — extracting ...",
              flush=True)
        records, chunks = _extract_book(pdf, cfg)
        _print_coverage(records)
        if action == "changed":
            delete_book(cfg.index_dir, book)
        append_chunks(chunks, embedder, cfg.index_dir, on_progress=progress)
        catalog.upsert_book(cfg.index_dir, book, h, cfg.embed_model,
                            len(chunks))
        changed_any = True

    if changed_any and table_exists(cfg.index_dir):
        print("\nRebuilding full-text index ...", flush=True)
        rebuild_fts(cfg.index_dir)
        if cfg.visual_retrieval:
            print("Note: visual index not refreshed on incremental runs — "
                  "run scripts.build_visual_index if you use the visual lane.")
    print(f"\nIndex up to date at {cfg.index_dir}")


def _print_coverage(records):
    print("\nCoverage report (ingest gate):")
    for book, stats in coverage_from_records(records).items():
        print(f"  {book}: {stats['pages_with_text']}/{stats['pages']} pages "
              f"with text ({stats['coverage'] * 100:.1f}%), "
              f"{stats['pages_with_figures']} figure pages")


def main():
    ap = argparse.ArgumentParser(description="Build or update the index.")
    ap.add_argument("--rebuild", action="store_true",
                    help="Re-extract and re-embed everything from scratch.")
    args = ap.parse_args()
    run(load_config(), rebuild=args.rebuild)


if __name__ == "__main__":
    main()
```

Notes for the implementer:
- The old script embedded the visual stage inside the build run, which once
  OOM-killed a 12 GB GPU holding both models; the incremental path now never
  loads BiomedCLIP (it points at `scripts.build_visual_index`), and the rebuild
  path keeps prior behavior only when `open_clip` is importable.
- `run()` accepts an injected `embedder` purely for tests.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_build_index.py -v`
Expected: all PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_index.py tests/test_build_index.py
git commit -m "feat: incremental per-book index build with --rebuild escape hatch"
```

---

### Task 7: Full-suite verification + README

**Files:**
- Modify: `README.md` (the "Build the index" section)

- [ ] **Step 1: Run the entire suite**

Run: `python3 -m pytest -q`
Expected: ALL tests pass (was 69 on `master` plus this plan's additions; no
skips beyond any pre-existing ones).

- [ ] **Step 2: Update README**

In `README.md`'s "Build the index" section, document the new behavior (adjust
surrounding prose to fit; keep the existing voice):

```markdown
Indexing is **incremental and resumable**: each book is hashed and recorded,
so re-running the command skips books that are already indexed, picks up new
or modified PDFs, and removes books you've deleted from the corpus folder. A
crash mid-build only costs you the book that was in flight — re-run and it
continues. To force a from-scratch rebuild (e.g. after changing
`EMBED_MODEL`): `python -m scripts.build_index --rebuild`.
```

- [ ] **Step 3: Sanity-check the real index is untouched and still queried fine**

Run: `python3 - <<'EOF'`
```python
from engine.config import load_config
from engine.catalog import catalog_embed_model
cfg = load_config()
print("catalog model:", catalog_embed_model(cfg.index_dir))   # None (pre-catalog)
from engine.index import Index
print("chunks rows:", Index(cfg.index_dir).tbl.count_rows())  # 26873
EOF
```
Expected: `catalog model: None` and the existing row count — proving backward
compatibility (no catalog yet ⇒ no mismatch error, index untouched).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README documents incremental indexing and --rebuild"
```
