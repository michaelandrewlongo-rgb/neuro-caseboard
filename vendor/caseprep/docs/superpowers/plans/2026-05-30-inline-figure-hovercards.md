# Inline Figure Hovercards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a self-contained `briefing.html` where clinically-salient words carry a hover superscript that reveals the single most semantically relevant figure (from `image_bank` or `textbook_figures`), each traceable to its source.

**Architecture:** A one-time offline build merges both figure corpora into a single local SQLite "figure store" (records + 768-d embeddings). The per-briefing path consumes that store: a salient-tag matcher marks words, a pure-Python cosine ranker picks the top-1 figure, and an HTML renderer post-processes the Markdown briefing to inject hover popovers. Every embedding-dependent unit takes an **injected embedder** so tests need no model/Postgres/GPU.

**Tech Stack:** Python 3.10+, `uv run pytest`, stdlib `sqlite3`/`array`/`struct`/`base64`/`html`/`re`, the `markdown` package (added as a dep), and — at real-build time only — `sentence-transformers` (`all-mpnet-base-v2`) + the Postgres/pgvector corpus.

**Test runner note:** `uv run pytest ...`. A harmless `ModuleNotFoundError: No module named 'cuda'` prints at startup — ignore it.

**Spec:** `docs/superpowers/specs/2026-05-30-inline-figure-hovercards-design.md`

**Design notes that bind the whole plan:**
- Shared record type `FigureRecord` (Task 1) is used by every task — keep its fields stable.
- Embeddings are stored/handled as **plain `list[float]`, normalized to unit length**, serialized as float32 via `array('f', ...)`. Cosine = dot product (vectors are unit-norm). No numpy anywhere in the committed code.
- Every unit that needs to embed text takes a parameter `embed_fn: Callable[[list[str]], list[list[float]]]`. Tests pass a deterministic stub; the real build passes `caseprep.image_bank.figure_embed.embed_texts`.

---

## File Structure

- `caseprep/image_bank/figure_store.py` (new) — `FigureRecord` + `FigureStore` (sqlite read/write). One responsibility: persistence + record shape.
- `caseprep/image_bank/figure_sources.py` (new) — adapters: `image_bank_records(...)`, `textbook_records(...)`. Turn each corpus into `FigureRecord`s.
- `caseprep/image_bank/figure_embed.py` (new) — the real `embed_texts` (lazy `sentence-transformers`). Imported only by the real build.
- `caseprep/image_bank/figure_build.py` (new) — `build_figure_store(...)` orchestrator + `__main__` CLI.
- `caseprep/figure_tags.py` (new) — salient-tag vocabulary + `find_marks`.
- `caseprep/figure_rank.py` (new) — pure-Python cosine `best_figure`.
- `caseprep/renderers/briefing_html.py` (new) — `render_briefing_html(...)` (md→html + hovercard injection).
- Tests: one file per unit under `tests/`.

---

## Task 0: Land the image-bank PR (controller step — NOT a TDD subagent task)

The cycle is built on `main` after PR #4 (image-bank infra) is merged. The controller performs this before dispatching any implementer subagent:

- [ ] Merge PR #4's branch (`worktree-image-bank-briefing-integration`) into `main`. It is a real merge (both branches touched `caseprep/schema.py`, `caseprep/core/builder.py`, `README.md`). Resolve conflicts preserving BOTH the image-bank work and the Cycle-1 prognostic work, then run the full suite (`uv run pytest -q`) and confirm green.
- [ ] Rebase/branch `inline-figure-hovercards` onto the merged `main`.

Note: the feature code below does **not** import PR #4 modules (it reads `bank.db` directly), so if the merge is contentious it does not block these tasks — but landing it first is the agreed sequence and avoids divergence.

---

## Task 1: FigureRecord + FigureStore (persistence)

**Files:**
- Create: `caseprep/image_bank/figure_store.py`
- Test: `tests/test_figure_store.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from pathlib import Path
from caseprep.image_bank.figure_store import FigureRecord, FigureStore


def _rec(key="image_bank:1", emb=(1.0, 0.0)):
    return FigureRecord(
        source="image_bank", fig_id=key.split(":", 1)[1],
        tags=["aspects", "mca occlusion"], caption="ASPECTS template",
        image_path="/imgs/a.jpg", image_blob=None,
        source_ref={"pmcid": "PMC1", "pmid": "9"}, embedding=list(emb),
    )


def test_write_then_load_roundtrip(tmp_path: Path):
    store = FigureStore(tmp_path / "fs.sqlite")
    n = store.write([_rec("image_bank:1", (0.6, 0.8)),
                     FigureRecord("textbook", "t1", ["thalamus"], "fig",
                                  "", b"\x89PNG...", {"heading_path": "Ch1>Fig2"},
                                  [0.0, 1.0])])
    assert n == 2
    recs = {FigureStore.key(r): r for r in FigureStore(tmp_path / "fs.sqlite").load()}
    assert set(recs) == {"image_bank:1", "textbook:t1"}
    a = recs["image_bank:1"]
    assert a.tags == ["aspects", "mca occlusion"]
    assert a.source_ref["pmcid"] == "PMC1"
    # embedding round-trips as unit-norm floats (0.6,0.8 already unit-norm)
    assert abs(a.embedding[0] - 0.6) < 1e-6 and abs(a.embedding[1] - 0.8) < 1e-6
    t = recs["textbook:t1"]
    assert t.image_blob == b"\x89PNG..." and t.image_path == ""


def test_key_format():
    assert FigureStore.key(_rec("image_bank:42")) == "image_bank:42"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_figure_store.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# caseprep/image_bank/figure_store.py
"""Local, offline figure store: one SQLite file holding merged figure records
from image_bank + textbook_figures, each with tags, caption, image, citation,
and a unit-norm 768-d embedding (stored as float32 bytes). No numpy."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class FigureRecord:
    source: str                      # "image_bank" | "textbook"
    fig_id: str
    tags: list[str]
    caption: str
    image_path: str                  # local file (image_bank); "" for textbook
    image_blob: bytes | None         # bytes (textbook); None for image_bank
    source_ref: dict[str, Any]       # {"pmcid","pmid"} or {"heading_path"}
    embedding: list[float] = field(default_factory=list)


def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


class FigureStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @staticmethod
    def key(rec: FigureRecord) -> str:
        return f"{rec.source}:{rec.fig_id}"

    def write(self, records: Iterable[FigureRecord]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".sqlite")
        os.close(fd)
        n = 0
        try:
            conn = sqlite3.connect(tmp)
            conn.execute(
                "CREATE TABLE figures (source TEXT, fig_id TEXT, tags TEXT, "
                "caption TEXT, image_path TEXT, image_blob BLOB, source_ref TEXT, "
                "embedding BLOB, PRIMARY KEY (source, fig_id))"
            )
            for r in records:
                conn.execute(
                    "INSERT OR REPLACE INTO figures VALUES (?,?,?,?,?,?,?,?)",
                    (r.source, r.fig_id, json.dumps(r.tags), r.caption,
                     r.image_path, r.image_blob, json.dumps(r.source_ref),
                     _pack(r.embedding)),
                )
                n += 1
            conn.commit()
            conn.close()
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return n

    def load(self) -> list[FigureRecord]:
        if not self.path.exists():
            return []
        conn = sqlite3.connect(self.path)
        rows = conn.execute(
            "SELECT source, fig_id, tags, caption, image_path, image_blob, "
            "source_ref, embedding FROM figures"
        ).fetchall()
        conn.close()
        out: list[FigureRecord] = []
        for src, fid, tags, cap, ipath, iblob, sref, emb in rows:
            out.append(FigureRecord(
                source=src, fig_id=fid, tags=json.loads(tags), caption=cap,
                image_path=ipath or "", image_blob=iblob,
                source_ref=json.loads(sref), embedding=_unpack(emb),
            ))
        return out
```

- [ ] **Step 4: Run → PASS** (`uv run pytest tests/test_figure_store.py -q`, 2 passed).
- [ ] **Step 5: Commit**

```bash
git add caseprep/image_bank/figure_store.py tests/test_figure_store.py
git commit -m "feat(figures): local FigureStore + FigureRecord (sqlite, float32 embeddings)"
```

---

## Task 2: image_bank → FigureRecords adapter

**Files:**
- Create: `caseprep/image_bank/figure_sources.py`
- Test: `tests/test_figure_sources_bank.py`

`tags` normalization: lowercase, strip, dedupe (order-preserving), drop empties. Parse a field that may be a JSON array (`["a","b"]`) or a comma string (`"a, b"`).

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
import sqlite3
from pathlib import Path
from caseprep.image_bank.figure_sources import image_bank_records, normalize_tags


def test_normalize_tags_handles_json_and_csv():
    assert normalize_tags('["MCA Occlusion", "ASPECTS"]', "thalamus, MCA Occlusion") == \
        ["mca occlusion", "aspects", "thalamus"]


def _bank(tmp: Path) -> Path:
    db = tmp / "bank.db"
    c = sqlite3.connect(db)
    c.executescript(
        "CREATE TABLE images (fig_id TEXT, cluster TEXT, pmcid TEXT, pmid TEXT, "
        "caption TEXT, local_path TEXT);"
        "CREATE TABLE labels (fig_id TEXT, is_neurosurgical INTEGER, anatomy TEXT, "
        "pathology TEXT, procedure TEXT, keywords TEXT, caption_summary TEXT);"
    )
    img = tmp / "a.jpg"; img.write_bytes(b"x")
    c.execute("INSERT INTO images VALUES ('f1','stroke','PMC1','9','cap',?)", (str(img),))
    c.execute("INSERT INTO labels VALUES ('f1',1,'[\"MCA\"]','[\"occlusion\"]',"
              "'thrombectomy','[\"ASPECTS\"]','short cap')")
    # a row whose image file is missing -> excluded
    c.execute("INSERT INTO images VALUES ('f2','stroke','PMC2','8','cap','/nope.jpg')")
    c.execute("INSERT INTO labels VALUES ('f2',1,'[]','[]','','[]','x')")
    c.commit(); c.close()
    return db


def test_image_bank_records(tmp_path: Path):
    db = _bank(tmp_path)
    stub = lambda texts: [[1.0, 0.0] for _ in texts]  # injected embedder
    recs = list(image_bank_records(sqlite3.connect(db), embed_fn=stub))
    assert len(recs) == 1  # f2 excluded (missing file)
    r = recs[0]
    assert r.source == "image_bank" and r.fig_id == "f1"
    assert "aspects" in r.tags and "mca" in r.tags and "thrombectomy" in r.tags
    assert r.source_ref == {"pmcid": "PMC1", "pmid": "9"}
    assert r.image_path.endswith("a.jpg") and r.image_blob is None
    assert r.embedding == [1.0, 0.0]
```

- [ ] **Step 2: Run → FAIL** (`uv run pytest tests/test_figure_sources_bank.py -q`).

- [ ] **Step 3: Implement** (create `figure_sources.py` with the bank adapter; the textbook adapter is added in Task 3 in the same file).

```python
# caseprep/image_bank/figure_sources.py
"""Adapters that turn each corpus into FigureRecords for the figure store."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]


def _parse_tagfield(value: Any) -> list[str]:
    if not value:
        return []
    text = str(value)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [part for part in text.split(",")]


def normalize_tags(*fields: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for f in fields:
        for raw in _parse_tagfield(f):
            t = raw.strip().lower()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def image_bank_records(conn: sqlite3.Connection, *, embed_fn: EmbedFn,
                       batch: int = 256) -> Iterator[FigureRecord]:
    cur = conn.execute(
        "SELECT i.fig_id, i.pmcid, i.pmid, i.local_path, i.caption, "
        "l.anatomy, l.pathology, l.procedure, l.keywords, l.caption_summary "
        "FROM images i JOIN labels l ON i.fig_id = l.fig_id "
        "WHERE l.is_neurosurgical = 1"
    )
    pending: list[tuple[FigureRecord, str]] = []

    def flush() -> Iterator[FigureRecord]:
        if not pending:
            return
        vecs = embed_fn([txt for _, txt in pending])
        for (rec, _), v in zip(pending, vecs):
            rec.embedding = list(v)
            yield rec
        pending.clear()

    for fig_id, pmcid, pmid, local_path, caption, anatomy, pathology, procedure, keywords, csum in cur:
        if not local_path or not Path(local_path).exists():
            continue
        tags = normalize_tags(keywords, anatomy, pathology, procedure)
        cap = str(csum or caption or "")
        rec = FigureRecord(
            source="image_bank", fig_id=str(fig_id), tags=tags, caption=cap,
            image_path=str(local_path), image_blob=None,
            source_ref={"pmcid": str(pmcid or ""), "pmid": str(pmid or "")},
            embedding=[],
        )
        pending.append((rec, cap or " "))
        if len(pending) >= batch:
            yield from flush()
    yield from flush()
```

- [ ] **Step 4: Run → PASS** (2 passed).
- [ ] **Step 5: Commit**

```bash
git add caseprep/image_bank/figure_sources.py tests/test_figure_sources_bank.py
git commit -m "feat(figures): image_bank -> FigureRecord adapter (injected embedder)"
```

---

## Task 3: textbook_figures → FigureRecords adapter

**Files:**
- Modify: `caseprep/image_bank/figure_sources.py` (add `textbook_records`)
- Test: `tests/test_figure_sources_textbook.py`

The adapter consumes an iterator of plain dict rows so it needs no live Postgres in tests. The real Postgres fetch is wired in Task 4.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from caseprep.image_bank.figure_sources import textbook_records


def _row(**kw):
    base = dict(id=1, caption_vlm="Tandem occlusion on CTA", caption="",
               heading_path="Stroke>Imaging>Fig3", vlm_keywords='["tandem occlusion","CTA"]',
               vlm_anatomy='["ICA"]', vlm_pathology='["occlusion"]', vlm_procedure="",
               embedding=[0.0, 1.0], image_data=b"\x89PNG")
    base.update(kw); return base


def test_textbook_records_maps_fields():
    recs = list(textbook_records([_row()]))
    assert len(recs) == 1
    r = recs[0]
    assert r.source == "textbook" and r.fig_id == "1"
    assert "tandem occlusion" in r.tags and "ica" in r.tags
    assert r.caption == "Tandem occlusion on CTA"
    assert r.source_ref == {"heading_path": "Stroke>Imaging>Fig3"}
    assert r.image_blob == b"\x89PNG" and r.image_path == ""
    assert r.embedding == [0.0, 1.0]


def test_textbook_skips_rows_without_embedding_or_image():
    assert list(textbook_records([_row(embedding=None)])) == []
    assert list(textbook_records([_row(image_data=None)])) == []
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** (append to `figure_sources.py`):

```python
def textbook_records(rows: Iterable[dict[str, Any]]) -> Iterator[FigureRecord]:
    for row in rows:
        emb = row.get("embedding")
        img = row.get("image_data")
        if not emb or not img:
            continue
        tags = normalize_tags(row.get("vlm_keywords"), row.get("vlm_anatomy"),
                              row.get("vlm_pathology"), row.get("vlm_procedure"))
        cap = str(row.get("caption_vlm") or row.get("caption") or "")
        yield FigureRecord(
            source="textbook", fig_id=str(row.get("id")), tags=tags, caption=cap,
            image_path="", image_blob=bytes(img),
            source_ref={"heading_path": str(row.get("heading_path") or "")},
            embedding=[float(x) for x in emb],
        )
```

- [ ] **Step 4: Run → PASS** (2 passed).
- [ ] **Step 5: Commit**

```bash
git add caseprep/image_bank/figure_sources.py tests/test_figure_sources_textbook.py
git commit -m "feat(figures): textbook_figures -> FigureRecord adapter (injected rows)"
```

---

## Task 4: Build orchestrator + real embedder + CLI

**Files:**
- Create: `caseprep/image_bank/figure_embed.py`
- Create: `caseprep/image_bank/figure_build.py`
- Test: `tests/test_figure_build.py`

The orchestrator is fully testable with injected fakes. The real embedder and the real Postgres fetch are thin, lazily-imported wrappers used only by the CLI (not exercised by tests, since `sentence-transformers`/Postgres are absent in CI).

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
import sqlite3
from pathlib import Path
from caseprep.image_bank.figure_build import build_figure_store
from caseprep.image_bank.figure_store import FigureStore


def _bank(tmp: Path) -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE images (fig_id TEXT, cluster TEXT, pmcid TEXT, pmid TEXT, caption TEXT, local_path TEXT);"
        "CREATE TABLE labels (fig_id TEXT, is_neurosurgical INTEGER, anatomy TEXT, pathology TEXT, procedure TEXT, keywords TEXT, caption_summary TEXT);"
    )
    img = tmp / "a.jpg"; img.write_bytes(b"x")
    c.execute("INSERT INTO images VALUES ('f1','s','PMC1','9','c',?)", (str(img),))
    c.execute("INSERT INTO labels VALUES ('f1',1,'[]','[]','','[\"aspects\"]','cap')")
    c.commit(); return c


def test_build_merges_both_sources(tmp_path: Path):
    out = tmp_path / "figure_store.sqlite"
    textbook = [dict(id=7, caption_vlm="fig", heading_path="H", vlm_keywords='["thalamus"]',
                     vlm_anatomy="", vlm_pathology="", vlm_procedure="",
                     embedding=[0.0, 1.0], image_data=b"PNG")]
    n = build_figure_store(
        out, bank_conn=_bank(tmp_path),
        embed_fn=lambda texts: [[1.0, 0.0] for _ in texts],
        textbook_rows=textbook,
    )
    assert n == 2
    keys = {FigureStore.key(r) for r in FigureStore(out).load()}
    assert keys == {"image_bank:f1", "textbook:7"}
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement**

```python
# caseprep/image_bank/figure_embed.py
"""Real text embedder (all-mpnet-base-v2, 768-d, unit-norm). Build-time only;
lazily imports sentence-transformers so the package import stays light."""
from __future__ import annotations

_MODEL = None
MODEL_NAME = "all-mpnet-base-v2"


def embed_texts(texts: list[str]) -> list[list[float]]:
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL_NAME)
    vecs = _MODEL.encode(texts, normalize_embeddings=True, batch_size=64)
    return [list(map(float, v)) for v in vecs]
```

```python
# caseprep/image_bank/figure_build.py
"""Offline build: merge image_bank + textbook_figures into one local FigureStore."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable

from caseprep.image_bank.figure_sources import EmbedFn, image_bank_records, textbook_records
from caseprep.image_bank.figure_store import FigureStore

_HERE = Path(__file__).resolve().parent
DEFAULT_BANK_DB = _HERE / "bank.db"
DEFAULT_STORE = _HERE / "figure_store.sqlite"


def build_figure_store(out_path: str | Path, *, bank_conn: sqlite3.Connection,
                       embed_fn: EmbedFn,
                       textbook_rows: Iterable[dict[str, Any]]) -> int:
    def all_records():
        yield from image_bank_records(bank_conn, embed_fn=embed_fn)
        yield from textbook_records(textbook_rows)
    return FigureStore(out_path).write(all_records())


def _fetch_textbook_rows() -> Iterable[dict[str, Any]]:  # pragma: no cover - needs Postgres
    import psycopg2
    from pgvector.psycopg2 import register_vector
    from caseprep.image_bank.textbook_embed import _db_kwargs
    conn = psycopg2.connect(**_db_kwargs())
    register_vector(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption_vlm, caption, heading_path, vlm_keywords, vlm_anatomy, "
        "vlm_pathology, vlm_procedure, embedding, image_data FROM textbook_figures "
        "WHERE embedding IS NOT NULL AND image_data IS NOT NULL"
    )
    cols = [d[0] for d in cur.description]
    for row in cur:
        d = dict(zip(cols, row))
        d["embedding"] = list(d["embedding"]) if d["embedding"] is not None else None
        yield d


def main() -> None:  # pragma: no cover - real build needs model + Postgres
    from caseprep.image_bank.figure_embed import embed_texts
    n = build_figure_store(
        DEFAULT_STORE, bank_conn=sqlite3.connect(DEFAULT_BANK_DB),
        embed_fn=embed_texts, textbook_rows=_fetch_textbook_rows(),
    )
    print(f"figure_store written: {n} figures -> {DEFAULT_STORE}")


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 4: Run → PASS** (1 passed). Also `uv run python -c "import caseprep.image_bank.figure_build"` must succeed.
- [ ] **Step 5: Commit**

```bash
git add caseprep/image_bank/figure_embed.py caseprep/image_bank/figure_build.py tests/test_figure_build.py
git commit -m "feat(figures): offline build orchestrator + real embedder + CLI"
```

---

## Task 5: Salient-tag vocabulary + matcher

**Files:**
- Create: `caseprep/figure_tags.py`
- Test: `tests/test_figure_tags.py`

Salience rule (precision over recall): a tag is eligible only if it is NOT in `STOP_TAGS`, is at least 4 chars, and is not a bare generic modality/word. Multi-word tags are always eligible (they're specific). Matching is whole-word, case-insensitive, **first occurrence in the document only**.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.figure_tags import build_vocabulary, find_marks, STOP_TAGS


def _rec(key, tags):
    s, i = key.split(":", 1)
    return FigureRecord(s, i, tags, "cap", "/x.jpg", None, {"pmcid": "P"}, [1.0, 0.0])


def test_vocabulary_filters_generic_keeps_clinical():
    recs = [_rec("image_bank:1", ["aspects", "mri", "patient", "tandem occlusion"]),
            _rec("textbook:2", ["aspects"])]
    vocab = build_vocabulary(recs)
    assert "mri" not in vocab and "patient" not in vocab        # generic dropped
    assert "aspects" in vocab and "tandem occlusion" in vocab   # clinical kept
    assert set(vocab["aspects"]) == {"image_bank:1", "textbook:2"}


def test_find_marks_whole_word_first_occurrence():
    recs = [_rec("image_bank:1", ["aspects"])]
    vocab = build_vocabulary(recs)
    text = "ASPECTS guides EVT. A second ASPECTS mention. Subaspects is not a hit."
    marks = find_marks(text, vocab)
    assert len(marks) == 1                       # first occurrence only
    m = marks[0]
    assert text[m.start:m.end].lower() == "aspects"
    assert m.start == 0                           # the first one
    assert m.candidate_keys == ["image_bank:1"]


def test_stop_tags_nonempty():
    assert "patient" in STOP_TAGS and "mri" in STOP_TAGS
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement**

```python
# caseprep/figure_tags.py
"""Salient-tag vocabulary + whole-word, first-occurrence matcher for figure marks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Generic words that must never mark a briefing word (precision guardrail).
STOP_TAGS: frozenset[str] = frozenset({
    "patient", "image", "imaging", "figure", "scan", "view", "mri", "ct", "cta",
    "ctp", "dsa", "angiogram", "angiography", "brain", "head", "left", "right",
    "axial", "coronal", "sagittal", "case", "study", "diagram", "illustration",
    "normal", "abnormal", "anatomy", "vessel", "artery", "vein",
})

MIN_TAG_LEN = 4


@dataclass
class Mark:
    term: str
    start: int
    end: int
    candidate_keys: list[str] = field(default_factory=list)


def _is_salient(tag: str) -> bool:
    if " " in tag:            # multi-word phrases are specific
        return True
    return len(tag) >= MIN_TAG_LEN and tag not in STOP_TAGS


def build_vocabulary(records) -> dict[str, list[str]]:
    """tag -> sorted list of figure keys carrying it (salient tags only)."""
    vocab: dict[str, list[str]] = {}
    for rec in records:
        key = f"{rec.source}:{rec.fig_id}"
        for tag in rec.tags:
            t = tag.strip().lower()
            if not _is_salient(t):
                continue
            vocab.setdefault(t, [])
            if key not in vocab[t]:
                vocab[t].append(key)
    return {t: sorted(keys) for t, keys in vocab.items()}


def find_marks(text: str, vocabulary: dict[str, list[str]]) -> list[Mark]:
    """First whole-word occurrence (in document order) of each salient term.
    Longer terms win when spans would overlap."""
    found: list[Mark] = []
    for term in sorted(vocabulary, key=len, reverse=True):
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        m = pattern.search(text)
        if m:
            found.append(Mark(term=term, start=m.start(), end=m.end(),
                              candidate_keys=list(vocabulary[term])))
    found.sort(key=lambda mk: mk.start)
    # drop overlaps (keep earlier/longer already prioritized)
    kept: list[Mark] = []
    last_end = -1
    for mk in found:
        if mk.start >= last_end:
            kept.append(mk)
            last_end = mk.end
    return kept
```

- [ ] **Step 4: Run → PASS** (3 passed).
- [ ] **Step 5: Commit**

```bash
git add caseprep/figure_tags.py tests/test_figure_tags.py
git commit -m "feat(figures): salient-tag vocabulary + whole-word first-occurrence matcher"
```

---

## Task 6: Semantic ranker (pure-Python cosine)

**Files:**
- Create: `caseprep/figure_rank.py`
- Test: `tests/test_figure_rank.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.figure_rank import best_figure


def _rec(key, emb, tags=("aspects",)):
    s, i = key.split(":", 1)
    return FigureRecord(s, i, list(tags), "cap", "/x.jpg", None, {"pmcid": "P"}, list(emb))


def test_best_figure_picks_highest_cosine():
    cands = [_rec("image_bank:1", [1.0, 0.0]), _rec("textbook:2", [0.0, 1.0])]
    stub = lambda texts: [[0.1, 0.99]]            # context near the 2nd vector
    r = best_figure("aspects in this case", cands, embed_fn=stub, floor=0.2)
    assert r is not None and r.fig_id == "2"


def test_best_figure_floor_returns_none():
    cands = [_rec("image_bank:1", [1.0, 0.0])]
    stub = lambda texts: [[0.0, 1.0]]             # orthogonal -> cosine 0
    assert best_figure("x", cands, embed_fn=stub, floor=0.2) is None


def test_fallback_when_no_embed_fn():
    cands = [_rec("image_bank:1", [1.0, 0.0], tags=["aspects"]),
             _rec("textbook:2", [0.0, 1.0], tags=["aspects", "collaterals"])]
    # context mentions 'collaterals' -> the 2nd record has more tag overlap
    r = best_figure("good collaterals here", cands, embed_fn=None, floor=0.2)
    assert r is not None and r.fig_id == "2"
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement**

```python
# caseprep/figure_rank.py
"""Pick the single most relevant figure for a term's context. Pure-Python cosine
over unit-norm embeddings; deterministic tag-overlap fallback when no embedder."""
from __future__ import annotations

import re
from typing import Callable

from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def best_figure(context: str, candidates: list[FigureRecord], *,
                embed_fn: EmbedFn | None, floor: float = 0.35) -> FigureRecord | None:
    if not candidates:
        return None
    if embed_fn is not None:
        q = embed_fn([context])[0]
        scored = [(_dot(q, c.embedding) if c.embedding else -1.0, c) for c in candidates]
        scored.sort(key=lambda sc: (-sc[0], f"{sc[1].source}:{sc[1].fig_id}"))
        top_score, top = scored[0]
        return top if top_score >= floor else None
    # fallback: most tag-token overlap with the context, then stable by key
    ctx = _tokens(context)
    def overlap(c: FigureRecord) -> int:
        return len(ctx & _tokens(" ".join(c.tags)))
    ranked = sorted(candidates, key=lambda c: (-overlap(c), f"{c.source}:{c.fig_id}"))
    return ranked[0] if overlap(ranked[0]) > 0 else ranked[0]
```

- [ ] **Step 4: Run → PASS** (3 passed).
- [ ] **Step 5: Commit**

```bash
git add caseprep/figure_rank.py tests/test_figure_rank.py
git commit -m "feat(figures): pure-Python cosine ranker with tag-overlap fallback"
```

---

## Task 7: HTML hovercard renderer

**Files:**
- Modify: `pyproject.toml` (add `markdown` dependency)
- Create: `caseprep/renderers/briefing_html.py`
- Test: `tests/test_briefing_html.py`

- [ ] **Step 1: Add the markdown dependency**

Run: `cd /home/michael/projects/caseprep/.claude/worktrees/image-bank-briefing-integration && uv add markdown`
Expected: `markdown` added to `pyproject.toml` + `uv.lock`. Verify `uv run python -c "import markdown"` succeeds.

- [ ] **Step 2: Write the failing test**

```python
from __future__ import annotations
import base64
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.renderers.briefing_html import render_briefing_html


def _store(tmp_img):
    return [FigureRecord("image_bank", "1", ["aspects"], "ASPECTS template",
                         str(tmp_img), None, {"pmcid": "PMC1", "pmid": "9"}, [1.0, 0.0]),
            FigureRecord("textbook", "2", ["collaterals"], "Collateral grading",
                         "", b"\x89PNG\r\n", {"heading_path": "Stroke>Fig1"}, [0.0, 1.0])]


def test_marks_term_with_embedded_image_and_source(tmp_path):
    img = tmp_path / "a.jpg"; img.write_bytes(b"JPEGBYTES")
    md = "## Imaging\n\nASPECTS guides EVT decisions.\n"
    html = render_briefing_html(md, _store(img),
                                embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" in html                       # hovercard injected
    assert "ASPECTS" in html
    assert "data:image" in html                      # image embedded (base64)
    assert base64.b64encode(b"JPEGBYTES").decode() in html
    assert "PMC1" in html                            # source credited
    # self-contained: no external file path leaks as an <img src>
    assert 'src="' + str(img) not in html


def test_unmatched_text_stays_plain(tmp_path):
    img = tmp_path / "a.jpg"; img.write_bytes(b"x")
    md = "## Plan\n\nNothing salient here.\n"
    html = render_briefing_html(md, _store(img), embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" not in html


def test_no_store_renders_plain_html(tmp_path):
    html = render_briefing_html("## H\n\nASPECTS.\n", [], embed_fn=None)
    assert "fig-card" not in html and "<h2" in html.lower()
```

- [ ] **Step 3: Run → FAIL**.

- [ ] **Step 4: Implement**

```python
# caseprep/renderers/briefing_html.py
"""Render the Markdown briefing to a self-contained HTML page with inline figure
hovercards: salient terms get a superscript; hovering reveals the top-1 figure."""
from __future__ import annotations

import base64
import html as _html
import re
from pathlib import Path
from typing import Callable

import markdown as _markdown

from caseprep.figure_rank import best_figure
from caseprep.figure_tags import build_vocabulary, find_marks
from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]

_CSS = """
<style>
.fig-term{position:relative;border-bottom:1px dotted #0a66c2;cursor:help}
.fig-term sup{color:#0a66c2;font-weight:bold}
.fig-term .fig-card{display:none;position:absolute;z-index:50;left:0;top:1.4em;
  width:520px;max-width:80vw;background:#fff;border:1px solid #ccc;border-radius:8px;
  box-shadow:0 6px 24px rgba(0,0,0,.25);padding:.6rem}
.fig-term:hover .fig-card{display:block}
.fig-card img{width:100%;height:auto;border-radius:4px}
.fig-card .cap{font-size:.85rem;color:#333;margin-top:.4rem}
@media (prefers-color-scheme: dark){.fig-card{background:#1e1e1e;border-color:#444}
  .fig-card .cap{color:#ccc}}
</style>
"""


def _data_uri(rec: FigureRecord) -> str | None:
    raw: bytes | None = None
    if rec.image_blob is not None:
        raw = rec.image_blob
    elif rec.image_path and Path(rec.image_path).exists():
        raw = Path(rec.image_path).read_bytes()
    if not raw:
        return None
    return "data:image/*;base64," + base64.b64encode(raw).decode("ascii")


def _source_html(rec: FigureRecord) -> str:
    ref = rec.source_ref
    pmcid = ref.get("pmcid")
    if pmcid:
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{_html.escape(pmcid)}/"
        return f'source: <a href="{url}">{_html.escape(pmcid)}</a>'
    if ref.get("heading_path"):
        return f"source: {_html.escape(str(ref['heading_path']))}"
    return ""


def _enclosing_sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right = min([p for p in (text.find(".", end), text.find("\n", end)) if p != -1] + [len(text)])
    return text[left:right].strip()


def _card_html(term: str, rec: FigureRecord) -> str | None:
    uri = _data_uri(rec)
    if uri is None:
        return None
    cap = _html.escape(rec.caption)
    src = _source_html(rec)
    return (f'<span class="fig-term">{_html.escape(term)}<sup>&#9638;</sup>'
            f'<span class="fig-card"><img src="{uri}" alt="{cap}">'
            f'<span class="cap">{cap}{(" — " + src) if src else ""}</span>'
            f"</span></span>")


def render_briefing_html(markdown_text: str, store_records: list[FigureRecord], *,
                         embed_fn: EmbedFn | None, floor: float = 0.35) -> str:
    body_md = markdown_text
    if store_records:
        vocab = build_vocabulary(store_records)
        by_key = {f"{r.source}:{r.fig_id}": r for r in store_records}
        marks = find_marks(markdown_text, vocab)
        # apply right-to-left so earlier offsets stay valid
        replacements: list[tuple[int, int, str]] = []
        for mk in marks:
            cands = [by_key[k] for k in mk.candidate_keys if k in by_key]
            ctx = _enclosing_sentence(markdown_text, mk.start, mk.end)
            chosen = best_figure(ctx, cands, embed_fn=embed_fn, floor=floor)
            if chosen is None:
                continue
            card = _card_html(markdown_text[mk.start:mk.end], chosen)
            if card is None:
                continue
            replacements.append((mk.start, mk.end, card))
        for start, end, card in sorted(replacements, key=lambda r: r[0], reverse=True):
            body_md = body_md[:start] + card + body_md[end:]
    body_html = _markdown.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{_CSS}</head><body>{body_html}</body></html>"
```

- [ ] **Step 5: Run → PASS** (3 passed).
- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock caseprep/renderers/briefing_html.py tests/test_briefing_html.py
git commit -m "feat(render): self-contained briefing.html with inline figure hovercards"
```

---

## Task 8: Wire the HTML export as a generation artifact + integration test

**Files:**
- Modify: `caseprep/renderers/markdown.py` (or the core writer that emits files) to also emit `briefing.html`
- Test: `tests/test_briefing_html_integration.py`

The export concatenates the rendered Markdown pages (the same `*.md` dict produced today) and runs `render_briefing_html` against the local figure store when present; absent store → it simply isn't emitted (no crash).

- [ ] **Step 1: Write the failing integration test**

```python
from __future__ import annotations
from caseprep.image_bank.figure_store import FigureRecord, FigureStore
from caseprep.renderers.briefing_html import render_briefing_html


def test_end_to_end_store_to_hovercard(tmp_path):
    img = tmp_path / "aspects.jpg"; img.write_bytes(b"IMGDATA")
    store_path = tmp_path / "figure_store.sqlite"
    FigureStore(store_path).write([
        FigureRecord("image_bank", "1", ["aspects"], "ASPECTS 10-point template",
                     str(img), None, {"pmcid": "PMC42", "pmid": "1"}, [1.0, 0.0]),
    ])
    records = FigureStore(store_path).load()
    md = "# Imaging Review\n\nReport the ASPECTS score before EVT.\n"
    html = render_briefing_html(md, records, embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" in html and "ASPECTS 10-point template" in html and "PMC42" in html
```

- [ ] **Step 2: Run → it should PASS already** (exercises Tasks 1–7 end to end). If it fails, fix the unit at fault, not the test.

- [ ] **Step 3: Emit the artifact in the file writer**

In the function that assembles the output `files` dict (the markdown renderer's `render_caseprep_files`, which returns the `*.md` mapping), add — guarded so absence of the store never breaks rendering:

```python
def maybe_briefing_html(files: dict[str, str], schema: dict) -> None:
    """Best-effort: emit briefing.html when a local figure store exists."""
    try:
        from pathlib import Path
        from caseprep.image_bank.figure_store import FigureStore
        from caseprep.image_bank.figure_build import DEFAULT_STORE
        from caseprep.renderers.briefing_html import render_briefing_html
        store = FigureStore(DEFAULT_STORE)
        records = store.load()
        if not records:
            return
        md = "\n\n".join(v for k, v in sorted(files.items()) if k.endswith(".md"))
        try:
            from caseprep.image_bank.figure_embed import embed_texts as ef
        except Exception:
            ef = None
        files["briefing.html"] = render_briefing_html(md, records, embed_fn=ef)
    except Exception:
        return  # never block the briefing on the HTML export
```

Call `maybe_briefing_html(files, schema)` just before `render_caseprep_files` returns its dict.

- [ ] **Step 4: Run** `uv run pytest tests/test_briefing_html_integration.py tests/test_briefing_html.py -q` → PASS. Confirm the existing renderer tests still pass: `uv run pytest tests/ -k "render or markdown" -q`.

- [ ] **Step 5: Commit**

```bash
git add caseprep/renderers/markdown.py tests/test_briefing_html_integration.py
git commit -m "feat(render): emit briefing.html artifact when a figure store is present"
```

---

## Final verification (after all tasks)

- [ ] `uv run pytest -q` — full suite green (slow; let it finish).
- [ ] **Real build (your environment — needs Postgres corpus + the embedding model):**
  `uv run --with sentence-transformers python -m caseprep.image_bank.figure_build`
  → writes `caseprep/image_bank/figure_store.sqlite`. Then regenerate a thrombectomy briefing and open `briefing.html`; confirm ASPECTS / occlusion terms reveal real, sourced figures on hover.

## Notes for the implementer

- **No numpy in committed code.** Embeddings are `list[float]`, unit-norm, float32-serialized; cosine is a dot product.
- **Injected embedders everywhere.** Tasks 2/4/6/7 take `embed_fn`; tests pass stubs. Only `figure_embed.py` / `figure_build.main` touch `sentence-transformers`, and only `figure_build._fetch_textbook_rows` touches Postgres — all `# pragma: no cover`.
- **Family-keyed later:** `build_vocabulary` currently uses one global salient filter; a `family` arg + per-family allow/deny lists is a clean later extension, not in this cycle (YAGNI).
- **Markdown injection caveat:** injecting a hovercard span into a Markdown **table row** (a line starting with `|`, e.g. the prognostic table's "ASPECTS" cells) or inside a ``` fence can break parsing. Guard it: in `render_briefing_html`, skip any mark whose **line** (the text from the preceding newline to the next) starts with `|` or lies within a fenced code block. Add a test: a term that appears only inside a `| ... |` row produces no hovercard. In practice the first occurrence is usually earlier prose, so this mainly protects the prognostic/decision tables.
