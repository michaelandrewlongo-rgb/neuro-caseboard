# Neurosurgery Textbook RAG — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local, citation-grounded retrieval tool that answers neurosurgery questions by synthesizing from 14 textbook PDFs, with answers tied to book/chapter/page.

**Architecture:** A decoupled `engine/` package (ingest → chunk → embed → LanceDB hybrid index → cross-encoder rerank → OpenRouter synthesis) exposing a single `query(question)` seam, plus thin `cli/` and `scripts/` wrappers. Embeddings and reranking run locally on the GPU; only retrieved excerpts are sent to OpenRouter.

**Tech Stack:** Python, PyMuPDF (fitz), sentence-transformers (BGE-large embeddings + BGE-reranker cross-encoder), LanceDB (vector + native FTS), OpenAI SDK pointed at OpenRouter, pytest.

---

## File Structure

```
neuro-textbook-rag/
├── requirements.txt
├── pytest.ini
├── .env.example
├── README.md
├── engine/
│   ├── __init__.py
│   ├── config.py        # .env parsing (CRLF-safe) + Config dataclass
│   ├── ingest.py        # PDF -> PageRecord (text + chapter from TOC); coverage report
│   ├── chunk.py         # PageRecord -> Chunk (page-exact)
│   ├── embed.py         # Embedder wrapper (injectable encoder)
│   ├── index.py         # RRF fusion + LanceDB build/hybrid search
│   ├── rerank.py        # Reranker wrapper (injectable scorer)
│   ├── synthesize.py    # grounded OpenRouter synthesis with citations
│   └── query.py         # Engine orchestration + public query()
├── cli/
│   ├── __init__.py
│   └── ask.py           # `python -m cli.ask "question"`
├── scripts/
│   ├── __init__.py
│   └── build_index.py   # full ingest+index pipeline + ingest gate report
├── eval/
│   ├── known_answers.yaml
│   └── run_eval.py      # retrieval gate + optional synthesis gate
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_ingest.py
    ├── test_chunk.py
    ├── test_embed.py
    ├── test_index.py
    ├── test_rerank.py
    ├── test_synthesize.py
    └── test_query.py
```

**Unit tests** inject fakes (fake encoder/scorer/LLM client) so they need no GPU or network. **Integration tests** (marked `@pytest.mark.integration`) exercise real LanceDB on a temp dir with a deterministic fake embedder.

---

## Task 0: Project scaffolding

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `engine/__init__.py`, `cli/__init__.py`, `scripts/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Write `requirements.txt`**

```
pymupdf>=1.24
sentence-transformers>=3.0
lancedb>=0.13
openai>=1.40
numpy>=1.26
pyyaml>=6.0
pytest>=8.0
```

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
pythonpath = .
markers =
    integration: requires real lancedb / models (deselect with -m "not integration")
```

- [ ] **Step 3: Create empty package markers**

Create `engine/__init__.py`, `cli/__init__.py`, `scripts/__init__.py` each containing a single comment line:

```python
# package marker
```

- [ ] **Step 4: Write `tests/conftest.py` (shared synthetic-PDF fixture)**

```python
import fitz
import pytest


@pytest.fixture
def tiny_pdf(tmp_path):
    """A 4-page PDF named 'Sample Book.pdf' with a 2-chapter TOC."""
    path = tmp_path / "Sample Book.pdf"
    doc = fitz.open()
    bodies = [
        "Introduction alpha: clinical content about diagnosis and patient management",
        "Introduction beta: imaging content about radiographic evaluation and findings",
        "Methods gamma: operative content about surgical technique and exposure steps",
        "Methods delta: content about postoperative care and complication management",
    ]
    for i, body in enumerate(bodies):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} {body}")
    doc.set_toc([[1, "Introduction", 1], [1, "Methods", 3]])
    doc.save(path)
    doc.close()
    return path
```

- [ ] **Step 5: Verify pytest collects with no tests yet**

Run: `cd ~/neuro-textbook-rag && python -m pytest -q`
Expected: `no tests ran` (exit code 5) — confirms config loads.

- [ ] **Step 6: Commit**

```bash
cd ~/neuro-textbook-rag
git add requirements.txt pytest.ini engine cli scripts tests
git commit -m "chore: project scaffolding and test fixtures"
```

---

## Task 1: Config (CRLF-safe .env loader)

**Files:**
- Create: `engine/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from engine.config import load_config


def test_env_file_crlf_and_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('OPENROUTER_API_KEY="sk-file"\r\nRETRIEVE_K=11\r\n')
    monkeypatch.delenv("RETRIEVE_K", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-proc")  # process env wins

    cfg = load_config(env_file=str(env))

    assert cfg.openrouter_api_key == "sk-proc"      # process env beats file
    assert cfg.retrieve_k == 11                      # from file
    assert "\r" not in cfg.openrouter_api_key
    assert cfg.embed_model == "BAAI/bge-large-en-v1.5"  # default


def test_missing_env_file_uses_defaults(tmp_path):
    cfg = load_config(env_file=str(tmp_path / "nope.env"))
    assert cfg.retrieve_k == 20
    assert cfg.rerank_k == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.config'`

- [ ] **Step 3: Write `engine/config.py`**

```python
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULTS = {
    "CORPUS_DIR": "/mnt/d/textbook_pdfs",
    "INDEX_DIR": str(Path.home() / "neuro-textbook-rag" / "index"),
    "EMBED_MODEL": "BAAI/bge-large-en-v1.5",
    "RERANK_MODEL": "BAAI/bge-reranker-v2-m3",
    "OPENROUTER_MODEL": "anthropic/claude-sonnet-4.6",
    "OPENROUTER_API_KEY": "",
    "CHUNK_MAX_WORDS": "600",
    "CHUNK_OVERLAP_WORDS": "80",
    "RETRIEVE_K": "20",
    "RERANK_K": "6",
    "EMBED_DEVICE": "cuda",
}


def _parse_env_file(path):
    env = {}
    p = Path(path)
    if not p.exists():
        return env
    for line in p.read_text().splitlines():
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'").replace("\r", "")
        env[key.strip()] = val
    return env


@dataclass
class Config:
    corpus_dir: Path
    index_dir: Path
    embed_model: str
    rerank_model: str
    openrouter_model: str
    openrouter_api_key: str
    chunk_max_words: int
    chunk_overlap_words: int
    retrieve_k: int
    rerank_k: int
    embed_device: str


def load_config(env_file=".env"):
    file_env = _parse_env_file(env_file)

    def get(key):
        if os.environ.get(key):
            return os.environ[key].replace("\r", "")
        if key in file_env:
            return file_env[key]
        return DEFAULTS[key]

    return Config(
        corpus_dir=Path(get("CORPUS_DIR")),
        index_dir=Path(get("INDEX_DIR")),
        embed_model=get("EMBED_MODEL"),
        rerank_model=get("RERANK_MODEL"),
        openrouter_model=get("OPENROUTER_MODEL"),
        openrouter_api_key=get("OPENROUTER_API_KEY"),
        chunk_max_words=int(get("CHUNK_MAX_WORDS")),
        chunk_overlap_words=int(get("CHUNK_OVERLAP_WORDS")),
        retrieve_k=int(get("RETRIEVE_K")),
        rerank_k=int(get("RERANK_K")),
        embed_device=get("EMBED_DEVICE"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/config.py tests/test_config.py
git commit -m "feat: CRLF-safe config loader with env precedence"
```

---

## Task 2: Ingest — extract pages with chapter labels

**Files:**
- Create: `engine/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py
from engine.ingest import extract_pages, coverage_report


def test_extract_pages_text_and_chapters(tiny_pdf):
    recs = extract_pages(tiny_pdf)
    assert len(recs) == 4
    assert recs[0].book == "Sample Book"
    assert recs[0].page == 1
    assert "alpha" in recs[0].text
    # TOC: pages 1-2 Introduction, pages 3-4 Methods
    assert recs[0].chapter == "Introduction"
    assert recs[1].chapter == "Introduction"
    assert recs[2].chapter == "Methods"
    assert recs[3].chapter == "Methods"


def test_coverage_report(tiny_pdf):
    rep = coverage_report(tiny_pdf.parent)
    assert "Sample Book" in rep
    assert rep["Sample Book"]["pages"] == 4
    assert rep["Sample Book"]["pages_with_text"] == 4
    assert rep["Sample Book"]["coverage"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.ingest'`

- [ ] **Step 3: Write `engine/ingest.py`**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import fitz  # PyMuPDF


@dataclass
class PageRecord:
    book: str
    page: int          # 1-based
    text: str
    chapter: Optional[str]


def _chapter_entries(doc):
    """Sorted (start_page_1based, title) from the PDF table of contents."""
    entries = []
    for _level, title, page in doc.get_toc():
        if page and page > 0:
            entries.append((page, title.strip()))
    entries.sort(key=lambda e: e[0])
    return entries


def _chapter_for_page(entries, page):
    chapter = None
    for start, title in entries:
        if start <= page:
            chapter = title
        else:
            break
    return chapter


def extract_pages(pdf_path):
    pdf_path = Path(pdf_path)
    book = pdf_path.stem
    doc = fitz.open(pdf_path)
    entries = _chapter_entries(doc)
    records = []
    for i in range(len(doc)):
        text = doc[i].get_text().strip()
        page = i + 1
        records.append(
            PageRecord(book=book, page=page, text=text,
                       chapter=_chapter_for_page(entries, page))
        )
    doc.close()
    return records


def iter_corpus(corpus_dir) -> Iterator[PageRecord]:
    for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
        for rec in extract_pages(pdf):
            yield rec


def coverage_report(corpus_dir):
    report = {}
    for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
        recs = extract_pages(pdf)
        total = len(recs)
        nonempty = sum(1 for r in recs if len(r.text) > 50)
        report[pdf.stem] = {
            "pages": total,
            "pages_with_text": nonempty,
            "coverage": round(nonempty / total, 3) if total else 0.0,
        }
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingest.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/ingest.py tests/test_ingest.py
git commit -m "feat: PDF ingest with TOC-derived chapter labels and coverage report"
```

---

## Task 3: Chunk — page-exact chunking

**Files:**
- Create: `engine/chunk.py`
- Test: `tests/test_chunk.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chunk.py
from engine.chunk import chunk_page, chunk_pages
from engine.ingest import PageRecord


def _rec(text, page=1, book="B", chapter="C"):
    return PageRecord(book=book, page=page, text=text, chapter=chapter)


def test_short_page_one_chunk():
    chunks = chunk_page(_rec("alpha beta gamma"), max_words=600, overlap=80)
    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert chunks[0].book == "B"
    assert chunks[0].chapter == "C"
    assert chunks[0].id == "B::p1::0"
    assert chunks[0].text == "alpha beta gamma"


def test_long_page_splits_with_overlap():
    words = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_page(_rec(words), max_words=600, overlap=80)
    assert len(chunks) == 2
    # second chunk starts at 600 - 80 = 520
    assert chunks[1].text.split()[0] == "w520"
    assert all(c.page == 1 for c in chunks)
    assert {c.id for c in chunks} == {"B::p1::0", "B::p1::1"}


def test_empty_page_no_chunks():
    assert chunk_page(_rec(""), max_words=600, overlap=80) == []


def test_chunk_pages_concatenates():
    recs = [_rec("a b c", page=1), _rec("d e f", page=2)]
    chunks = chunk_pages(recs, max_words=600, overlap=80)
    assert [c.page for c in chunks] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chunk.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.chunk'`

- [ ] **Step 3: Write `engine/chunk.py`**

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class Chunk:
    id: str
    book: str
    chapter: Optional[str]
    page: int
    text: str


def chunk_page(record, max_words, overlap):
    words = record.text.split()
    if not words:
        return []
    step = max(1, max_words - overlap)
    chunks = []
    idx = 0
    start = 0
    while start < len(words):
        text = " ".join(words[start:start + max_words])
        chunks.append(Chunk(
            id=f"{record.book}::p{record.page}::{idx}",
            book=record.book,
            chapter=record.chapter,
            page=record.page,
            text=text,
        ))
        idx += 1
        if start + max_words >= len(words):
            break
        start += step
    return chunks


def chunk_pages(records, max_words, overlap):
    out = []
    for rec in records:
        out.extend(chunk_page(rec, max_words, overlap))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chunk.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/chunk.py tests/test_chunk.py
git commit -m "feat: page-exact word-based chunking with overlap"
```

---

## Task 4: Embed — injectable embedder wrapper

**Files:**
- Create: `engine/embed.py`
- Test: `tests/test_embed.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embed.py
import numpy as np
from engine.embed import Embedder, QUERY_PREFIX


class FakeEncoder:
    def __init__(self):
        self.seen = []

    def encode(self, texts, normalize_embeddings=False):
        self.seen.append((list(texts), normalize_embeddings))
        return np.array([[float(len(t)), 1.0] for t in texts])


def test_embed_texts_shape_and_dtype():
    enc = FakeEncoder()
    emb = Embedder("fake", encoder=enc)
    vecs = emb.embed_texts(["aa", "bbbb"])
    assert vecs.shape == (2, 2)
    assert vecs.dtype == np.float32
    assert enc.seen[0][1] is True  # normalize_embeddings passed


def test_embed_query_applies_prefix():
    enc = FakeEncoder()
    emb = Embedder("fake", encoder=enc)
    vec = emb.embed_query("aneurysm clipping")
    assert vec.shape == (2,)
    assert enc.seen[0][0][0] == QUERY_PREFIX + "aneurysm clipping"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_embed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.embed'`

- [ ] **Step 3: Write `engine/embed.py`**

```python
import numpy as np

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, model_name, device="cpu", encoder=None):
        self.model_name = model_name
        self.device = device
        self._encoder = encoder

    @property
    def encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self.model_name, device=self.device)
        return self._encoder

    def embed_texts(self, texts):
        vecs = self.encoder.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")

    def embed_query(self, text):
        vecs = self.encoder.encode([QUERY_PREFIX + text], normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_embed.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/embed.py tests/test_embed.py
git commit -m "feat: injectable BGE embedder wrapper with query prefix"
```

---

## Task 5: Index — RRF fusion (pure) + LanceDB hybrid search

**Files:**
- Create: `engine/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing test (pure RRF unit + lancedb integration)**

```python
# tests/test_index.py
import numpy as np
import pytest
from engine.index import reciprocal_rank_fusion, build_index, Index
from engine.chunk import Chunk


def test_rrf_rewards_agreement():
    # 'b' is high in both rankings -> should win
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    ids = [i for i, _ in fused]
    assert ids[0] == "b"
    assert set(ids) == {"a", "b", "c", "d"}


class FakeEmbedder:
    """Deterministic 2-D vectors so vector search is predictable."""
    def __init__(self):
        self.table = {
            "icp": [1.0, 0.0],
            "spine": [0.0, 1.0],
        }

    def embed_texts(self, texts):
        out = []
        for t in texts:
            out.append([1.0, 0.0] if "icp" in t.lower() else [0.0, 1.0])
        return np.array(out, dtype="float32")

    def embed_query(self, text):
        return np.array(self.table["icp" if "icp" in text.lower() else "spine"],
                        dtype="float32")


@pytest.mark.integration
def test_build_and_hybrid_search(tmp_path):
    chunks = [
        Chunk(id="x::p1::0", book="NeuroICU", chapter="Pressure",
              page=10, text="normal icp range is 5 to 15 mmHg"),
        Chunk(id="y::p2::0", book="Benzel", chapter="Fusion",
              page=20, text="spine pedicle screw fixation technique"),
    ]
    emb = FakeEmbedder()
    build_index(chunks, emb, tmp_path / "idx")
    idx = Index(tmp_path / "idx")

    hits = idx.hybrid_search("what is normal icp", emb.embed_query("icp"), k=2)
    assert hits[0].book == "NeuroICU"
    assert hits[0].page == 10
    assert hits[0].chapter == "Pressure"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_index.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.index'`

- [ ] **Step 3: Write `engine/index.py`**

```python
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


def reciprocal_rank_fusion(rankings, k=60):
    """rankings: list of id-lists, each ordered best-first.
    Returns [(id, fused_score)] sorted descending."""
    scores = {}
    for ranking in rankings:
        for rank, _id in enumerate(ranking):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def build_index(chunks, embedder, index_dir, batch_size=256):
    db = lancedb.connect(str(index_dir))
    texts = [c.text for c in chunks]
    vectors = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(embedder.embed_texts(texts[i:i + batch_size]))
    rows = []
    for c, v in zip(chunks, vectors):
        rows.append({
            "id": c.id,
            "book": c.book,
            "chapter": c.chapter or "",
            "page": int(c.page),
            "text": c.text,
            "vector": [float(x) for x in v],
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
```

- [ ] **Step 4: Run tests (unit always; integration once lancedb is installed)**

Run: `python -m pytest tests/test_index.py -q`
Expected: PASS (2 passed). If lancedb's FTS API differs in the installed version, fix `text_search` to match the installed `query_type="fts"` signature before moving on.

- [ ] **Step 5: Commit**

```bash
git add engine/index.py tests/test_index.py
git commit -m "feat: LanceDB hybrid index with reciprocal rank fusion"
```

---

## Task 6: Rerank — injectable cross-encoder

**Files:**
- Create: `engine/rerank.py`
- Test: `tests/test_rerank.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rerank.py
from engine.rerank import Reranker
from engine.index import Hit


class FakeScorer:
    """Scores by presence of 'good' in the passage text."""
    def predict(self, pairs):
        return [10.0 if "good" in text else 0.0 for _q, text in pairs]


def _hit(id_, text):
    return Hit(id=id_, book="B", chapter="C", page=1, text=text)


def test_rerank_orders_and_truncates():
    hits = [_hit("1", "bad"), _hit("2", "good match"), _hit("3", "bad")]
    out = Reranker("fake", scorer=FakeScorer()).rerank("q", hits, top_k=2)
    assert len(out) == 2
    assert out[0].id == "2"
    assert out[0].score == 10.0


def test_rerank_empty():
    assert Reranker("fake", scorer=FakeScorer()).rerank("q", [], top_k=3) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rerank.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.rerank'`

- [ ] **Step 3: Write `engine/rerank.py`**

```python
class Reranker:
    def __init__(self, model_name, device="cpu", scorer=None):
        self.model_name = model_name
        self.device = device
        self._scorer = scorer

    @property
    def scorer(self):
        if self._scorer is None:
            from sentence_transformers import CrossEncoder
            self._scorer = CrossEncoder(self.model_name, device=self.device)
        return self._scorer

    def rerank(self, query, hits, top_k):
        if not hits:
            return []
        pairs = [(query, h.text) for h in hits]
        scores = self.scorer.predict(pairs)
        ranked = sorted(zip(hits, scores), key=lambda hs: float(hs[1]), reverse=True)
        out = []
        for hit, score in ranked[:top_k]:
            hit.score = float(score)
            out.append(hit)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rerank.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/rerank.py tests/test_rerank.py
git commit -m "feat: injectable cross-encoder reranker"
```

---

## Task 7: Synthesize — grounded OpenRouter answer with citations

**Files:**
- Create: `engine/synthesize.py`
- Test: `tests/test_synthesize.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synthesize.py
from engine.synthesize import synthesize, SYSTEM_PROMPT
from engine.index import Hit


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeClient:
    def __init__(self):
        self.captured = {}
        self.chat = self  # so client.chat.completions.create resolves
        self.completions = self

    def create(self, model, messages, temperature):
        self.captured = {"model": model, "messages": messages,
                         "temperature": temperature}
        return FakeCompletion("ICP is 5-15 mmHg [1].")


def _hit():
    return Hit(id="x", book="NeuroICU", chapter="Pressure", page=10,
               text="normal icp is 5 to 15 mmHg")


def test_synthesize_builds_prompt_and_citations():
    client = FakeClient()
    out = synthesize("normal icp?", [_hit()], client, "anthropic/claude-sonnet-4.6")

    assert out.answer == "ICP is 5-15 mmHg [1]."
    assert client.captured["model"] == "anthropic/claude-sonnet-4.6"
    sys_msg = client.captured["messages"][0]
    user_msg = client.captured["messages"][1]
    assert sys_msg["content"] == SYSTEM_PROMPT
    assert "[1] NeuroICU, Pressure, p.10" in user_msg["content"]
    assert "normal icp is 5 to 15 mmHg" in user_msg["content"]

    assert len(out.citations) == 1
    assert out.citations[0].n == 1
    assert out.citations[0].book == "NeuroICU"
    assert out.citations[0].page == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_synthesize.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.synthesize'`

- [ ] **Step 3: Write `engine/synthesize.py`**

```python
from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are a neurosurgical reference assistant. Answer ONLY from the provided "
    "textbook passages. Rules:\n"
    "- Cite the bracketed source number for every clinical claim, e.g. [2].\n"
    "- If the passages do not contain the answer, say "
    "\"Not found in the provided sources.\"\n"
    "- If sources disagree, state the disagreement explicitly and attribute each "
    "view to its source.\n"
    "- Be concise and clinically precise. This is decision-support, not a "
    "substitute for clinical judgment."
)


@dataclass
class Citation:
    n: int
    book: str
    chapter: str
    page: int


@dataclass
class Synthesis:
    answer: str
    citations: list = field(default_factory=list)


def _format_passages(hits):
    lines = []
    for i, h in enumerate(hits, 1):
        loc = h.book
        if h.chapter:
            loc += f", {h.chapter}"
        loc += f", p.{h.page}"
        lines.append(f"[{i}] {loc}:\n{h.text}")
    return "\n\n".join(lines)


def synthesize(question, hits, client, model):
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    )
    answer = resp.choices[0].message.content
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    return Synthesis(answer=answer, citations=citations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_synthesize.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/synthesize.py tests/test_synthesize.py
git commit -m "feat: grounded synthesis with citation guardrails"
```

---

## Task 8: Query — Engine orchestration + public seam

**Files:**
- Create: `engine/query.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query.py
from engine.query import Engine, QueryResult
from engine.index import Hit
from engine.synthesize import Synthesis, Citation


class FakeConfig:
    retrieve_k = 5
    rerank_k = 2
    openrouter_model = "m"


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0, 1.0]


class FakeIndex:
    def __init__(self):
        self.called_with = None

    def hybrid_search(self, query_text, query_vector, k):
        self.called_with = (query_text, query_vector, k)
        return [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
                Hit(id="b", book="B", chapter="C", page=2, text="t2")]


class FakeReranker:
    def rerank(self, query, hits, top_k):
        return hits[:top_k]


def fake_synth(question, hits, client, model):
    return Synthesis(answer=f"ans:{len(hits)}",
                     citations=[Citation(1, "B", "C", 1)])


def test_engine_query_orchestration():
    index = FakeIndex()
    engine = Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                    client=None, synth_fn=fake_synth)
    result = engine.query("normal icp?")

    assert isinstance(result, QueryResult)
    assert result.answer == "ans:2"
    assert index.called_with == ("normal icp?", [0.0, 1.0], 5)
    assert len(result.citations) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_query.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.query'`

- [ ] **Step 3: Write `engine/query.py`**

```python
from dataclasses import dataclass, field

from .config import load_config
from .embed import Embedder
from .index import Index
from .rerank import Reranker
from .synthesize import synthesize


@dataclass
class QueryResult:
    answer: str
    citations: list = field(default_factory=list)


class Engine:
    def __init__(self, config, embedder, index, reranker, client,
                 synth_fn=synthesize):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.client = client
        self.synth_fn = synth_fn

    def query(self, question):
        qv = self.embedder.embed_query(question)
        hits = self.index.hybrid_search(question, qv, self.config.retrieve_k)
        top = self.reranker.rerank(question, hits, self.config.rerank_k)
        syn = self.synth_fn(question, top, self.client,
                            self.config.openrouter_model)
        return QueryResult(answer=syn.answer, citations=syn.citations)


_engine = None


def get_engine(config=None):
    global _engine
    if _engine is not None:
        return _engine
    config = config or load_config()
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=config.openrouter_api_key)
    embedder = Embedder(config.embed_model, device=config.embed_device)
    index = Index(config.index_dir)
    reranker = Reranker(config.rerank_model, device=config.embed_device)
    _engine = Engine(config, embedder, index, reranker, client)
    return _engine


def query(question, config=None):
    return get_engine(config).query(question)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_query.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the whole unit suite (exclude integration)**

Run: `python -m pytest -q -m "not integration"`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add engine/query.py tests/test_query.py
git commit -m "feat: engine orchestration and public query seam"
```

---

## Task 9: Build-index script (ingest gate)

**Files:**
- Create: `scripts/build_index.py`

- [ ] **Step 1: Write `scripts/build_index.py`**

```python
from engine.config import load_config
from engine.ingest import iter_corpus, coverage_report
from engine.chunk import chunk_pages
from engine.embed import Embedder
from engine.index import build_index


def main():
    cfg = load_config()
    print("Coverage report (ingest gate):")
    for book, stats in coverage_report(cfg.corpus_dir).items():
        print(f"  {book}: {stats['pages_with_text']}/{stats['pages']} pages "
              f"with text ({stats['coverage'] * 100:.1f}%)")

    records = list(iter_corpus(cfg.corpus_dir))
    chunks = chunk_pages(records, cfg.chunk_max_words, cfg.chunk_overlap_words)
    print(f"Total pages: {len(records)} | total chunks: {len(chunks)}")

    embedder = Embedder(cfg.embed_model, device=cfg.embed_device)
    build_index(chunks, embedder, cfg.index_dir)
    print(f"Index built at {cfg.index_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run on the real corpus (this downloads the embedding model and builds the index)**

Run: `cd ~/neuro-textbook-rag && python -m scripts.build_index`
Expected: a per-book coverage table (14 books, each high coverage), a chunk count, and "Index built at …/index". If any book shows <50% coverage, note it as an OCR candidate (deferred — do not block).

- [ ] **Step 3: Commit**

```bash
git add scripts/build_index.py
git commit -m "feat: build-index pipeline with ingest-gate coverage report"
```

---

## Task 10: CLI

**Files:**
- Create: `cli/ask.py`

- [ ] **Step 1: Write `cli/ask.py`**

```python
import argparse

from engine.query import query


def main():
    ap = argparse.ArgumentParser(
        description="Ask the neurosurgery textbook RAG a clinical question.")
    ap.add_argument("question", help="The clinical question, in quotes")
    args = ap.parse_args()

    result = query(args.question)
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test against the built index (requires OPENROUTER_API_KEY in .env)**

Run: `python -m cli.ask "What is the normal range for intracranial pressure in adults?"`
Expected: a concise answer with bracketed citations, followed by a Sources list naming the NeuroICU book and a page. Verify the cited page by opening the PDF.

- [ ] **Step 3: Commit**

```bash
git add cli/ask.py
git commit -m "feat: ask CLI"
```

---

## Task 11: Evaluation harness (retrieval + synthesis gates)

**Files:**
- Create: `eval/known_answers.yaml`, `eval/run_eval.py`

- [ ] **Step 1: Write `eval/known_answers.yaml`**

```yaml
# Each case: a question + a substring expected to appear in a retrieved book name.
# Tune expected books to your corpus after first run.
- question: "What is the normal range for intracranial pressure in adults?"
  expect_book_contains: "NeuroICU"
- question: "Describe pedicle screw placement technique in the lumbar spine."
  expect_book_contains: "Benzel"
- question: "What is the Spetzler-Martin grading scale for arteriovenous malformations?"
  expect_book_contains: "neurovascular"
- question: "What are the components of the WHO grading of meningiomas?"
  expect_book_contains: "Greenberg"
```

- [ ] **Step 2: Write `eval/run_eval.py`**

```python
import argparse

import yaml

from engine.query import get_engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval/known_answers.yaml")
    ap.add_argument("--synthesize", action="store_true",
                    help="Also call the LLM and print answers for blinded review")
    args = ap.parse_args()

    cases = yaml.safe_load(open(args.set))
    engine = get_engine()
    passed = 0
    for case in cases:
        q = case["question"]
        qv = engine.embedder.embed_query(q)
        hits = engine.index.hybrid_search(q, qv, engine.config.retrieve_k)
        top = engine.reranker.rerank(q, hits, engine.config.rerank_k)
        books = [h.book for h in top]
        want = case["expect_book_contains"].lower()
        ok = any(want in b.lower() for b in books)
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"    top books: {books}")
        if args.synthesize:
            print(f"    answer: {engine.query(q).answer[:600]}\n")
    print(f"\nRetrieval gate: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the retrieval gate**

Run: `python -m eval.run_eval`
Expected: a PASS/FAIL line per case and a summary. Investigate any FAIL (wrong book retrieved) before trusting synthesis. Then run `python -m eval.run_eval --synthesize` and eyeball each answer against its citations (synthesis gate — blinded faithfulness check).

- [ ] **Step 4: Commit**

```bash
git add eval/known_answers.yaml eval/run_eval.py
git commit -m "feat: retrieval and synthesis evaluation gates"
```

---

## Task 12: Docs and env template

**Files:**
- Create: `.env.example`, `README.md`

- [ ] **Step 1: Write `.env.example`**

```
# Copy to .env and fill in. Values are CRLF-stripped automatically.
OPENROUTER_API_KEY=
OPENROUTER_MODEL=anthropic/claude-sonnet-4.6
CORPUS_DIR=/mnt/d/textbook_pdfs
INDEX_DIR=/home/michael/neuro-textbook-rag/index
EMBED_MODEL=BAAI/bge-large-en-v1.5
RERANK_MODEL=BAAI/bge-reranker-v2-m3
EMBED_DEVICE=cuda
RETRIEVE_K=20
RERANK_K=6
CHUNK_MAX_WORDS=600
CHUNK_OVERLAP_WORDS=80
```

- [ ] **Step 2: Write `README.md`**

````markdown
# Neurosurgery Textbook RAG

Local, citation-grounded Q&A over a folder of neurosurgery textbooks. Embeddings
and reranking run locally on the GPU; only retrieved excerpts are sent to
OpenRouter for synthesis.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your OPENROUTER_API_KEY
```

## Build the index (one-time, re-run when books change)

```bash
python -m scripts.build_index
```

## Ask a question

```bash
python -m cli.ask "What is the normal range for intracranial pressure in adults?"
```

## Validate

```bash
python -m pytest -q -m "not integration"   # fast unit tests
python -m pytest -q                          # include lancedb integration
python -m eval.run_eval                      # retrieval gate
python -m eval.run_eval --synthesize         # synthesis gate (blinded review)
```

## Design

See `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-design.md`.
Phase 2 (figure/atlas visual retrieval) attaches at the `engine.query` seam.
````

- [ ] **Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs: README and env template"
```

---

## Self-Review Notes

- **Spec coverage:** ingest+chapters (T2), local embeddings (T4), LanceDB hybrid retrieval (T5), reranker (T6), OpenRouter grounded synthesis with citations/refusal/disagreement (T7), CLI seam + future phone/figure seam via `Engine`/`query` (T8/T10), ingest gate (T9), retrieval+synthesis gates (T11), CRLF-safe `.env` (T1). All spec sections map to a task.
- **Naming consistency:** `Hit`, `Chunk`, `PageRecord`, `Citation`, `Synthesis`, `QueryResult`, `Engine.query`, `hybrid_search`, `rerank`, `embed_query`/`embed_texts`, `build_index` used identically across tasks.
- **Known version risk:** LanceDB's FTS API (`query_type="fts"`, `create_fts_index`) varies by version — T5 Step 4 calls this out explicitly as the one place to adapt to the installed version.
- **Deferred (out of scope, intentional):** OCR fallback beyond the coverage flag, phone/web UI, figure retrieval (phase 2).
