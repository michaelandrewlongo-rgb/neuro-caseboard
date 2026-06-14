# Phase 2b — Visual Retrieval Lane (Approach B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, swappable visual retrieval lane so textbook atlas plates surface on image similarity to the query (fixing Phase 2a's text-driven misses), changing only which figures are attached — not the worded answer.

**Architecture:** A new `figures` LanceDB table holds one CLIP-image embedding per figure page (built from Phase 2a's cached PNGs). At query time the question is embedded with the CLIP text tower, image-searched against that table, and the visual hits are RRF-fused with the figure-bearing text hits to pick the attached figures. Visual-only figures become appended citable sources. The text answer path is untouched; the lane degrades gracefully if the table is absent or `VISUAL_RETRIEVAL` is off.

**Tech Stack:** Python, open_clip_torch (BiomedCLIP/SigLIP/OpenCLIP), LanceDB, PyMuPDF, google-genai (Vertex), pytest.

**Spec:** `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-phase2b-visual-retrieval-design.md`

**Conventions from earlier phases to follow:**
- Dependency injection for testability: heavy models are injectable (`Embedder(encoder=...)`); real model/network code is NOT unit-tested — it's covered by the eval gates. The visual embedder follows the same pattern via an injectable `backend`.
- New dataclass fields are added with defaults.
- LanceDB round-trips get a `@pytest.mark.integration` test.
- Use `python3` (not `python`). Run the FULL suite (`python3 -m pytest -q`) before each commit.
- Reuse the existing module-level `reciprocal_rank_fusion(rankings)` in `engine/index.py` for figure fusion.

**Note on open_clip:** `OpenClipBackend` (Task 2) targets `open_clip_torch >= 2.24`: `open_clip.create_model_from_pretrained(model_name)` → `(model, preprocess)`, `open_clip.get_tokenizer(model_name)`, `model.encode_image(tensor)`, `model.encode_text(tokens)`. It is not unit-tested (no model download in tests); the figure gate validates it. If the installed API differs, fix only the backend's SDK calls, not the tested `VisualEmbedder` contract.

---

### Task 1: Config and dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `engine/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_phase2b_visual_defaults(tmp_path):
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.visual_model  # non-empty default
    assert cfg.visual_retrieve_k == 10
    assert cfg.visual_retrieval is True


def test_visual_retrieval_toggle_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("VISUAL_RETRIEVAL=off\nVISUAL_RETRIEVE_K=5\n")
    cfg = load_config(env_file=str(env))
    assert cfg.visual_retrieval is False
    assert cfg.visual_retrieve_k == 5
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_config.py::test_phase2b_visual_defaults -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'visual_model'`.

- [ ] **Step 3: Add the config fields**

In `engine/config.py`, add to `DEFAULTS`:

```python
    "VISUAL_MODEL": "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
    "VISUAL_RETRIEVE_K": "10",
    "VISUAL_RETRIEVAL": "true",
```

Add to the `Config` dataclass fields:

```python
    visual_model: str
    visual_retrieve_k: int
    visual_retrieval: bool
```

Add to the `Config(...)` construction in `load_config`:

```python
        visual_model=get("VISUAL_MODEL"),
        visual_retrieve_k=int(get("VISUAL_RETRIEVE_K")),
        visual_retrieval=get("VISUAL_RETRIEVAL").strip().lower() in
        ("1", "true", "yes", "on"),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Update requirements and .env.example**

Append to `requirements.txt`:

```
open_clip_torch>=2.24
```

Append to `.env.example`:

```
# Phase 2b — visual retrieval lane
VISUAL_MODEL=hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224
VISUAL_RETRIEVE_K=10
VISUAL_RETRIEVAL=true
```

- [ ] **Step 6: Install the dependency**

Run: `python3 -m pip install -r requirements.txt`
Expected: `open_clip_torch` installs without error. (If it fails on network/env, still complete code+test+commit and report as a concern.)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt engine/config.py .env.example tests/test_config.py
git commit -m "feat: Phase 2b config (visual model/knobs) and open_clip dep"
```

---

### Task 2: Visual embedder (`engine/visual_embed.py`)

**Files:**
- Create: `engine/visual_embed.py`
- Test: `tests/test_visual_embed.py`

`VisualEmbedder` delegates the model work to an injectable `backend` (default `OpenClipBackend`), and owns only L2-normalization + numpy shaping — which is what we unit-test. `OpenClipBackend` (the real open_clip code) is not unit-tested.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_visual_embed.py`:

```python
import numpy as np

from engine.visual_embed import VisualEmbedder, _l2_normalize


class FakeBackend:
    """Returns fixed RAW (un-normalized) vectors so we can test normalization."""
    def encode_images(self, paths):
        # one row per path; magnitudes != 1 so normalization is observable
        return np.array([[3.0, 4.0]] * len(paths), dtype="float32")

    def encode_text(self, text):
        return np.array([0.0, 2.0], dtype="float32")


def test_l2_normalize_unit_rows():
    out = _l2_normalize(np.array([[3.0, 4.0], [0.0, 0.0]], dtype="float32"))
    assert np.allclose(np.linalg.norm(out, axis=1), [1.0, 0.0])  # zero row stays zero


def test_embed_images_normalized_shape():
    emb = VisualEmbedder("dummy-model", backend=FakeBackend())
    vecs = emb.embed_images(["a.png", "b.png"])
    assert vecs.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vecs, axis=1), [1.0, 1.0])
    assert np.allclose(vecs[0], [0.6, 0.8])


def test_embed_images_empty_returns_empty():
    emb = VisualEmbedder("dummy-model", backend=FakeBackend())
    out = emb.embed_images([])
    assert out.shape[0] == 0


def test_embed_query_is_unit_vector_1d():
    emb = VisualEmbedder("dummy-model", backend=FakeBackend())
    v = emb.embed_query("cavernous sinus")
    assert v.shape == (2,)
    assert np.allclose(v, [0.0, 1.0])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_visual_embed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.visual_embed'`.

- [ ] **Step 3: Implement `engine/visual_embed.py`**

```python
import numpy as np

from .config import resolve_device


def _l2_normalize(arr):
    arr = np.asarray(arr, dtype="float32")
    if arr.size == 0:
        return arr
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


class OpenClipBackend:
    """Real open_clip backend (BiomedCLIP / SigLIP / OpenCLIP). Not unit-tested;
    validated by the figure gate. Targets open_clip_torch >= 2.24."""

    def __init__(self, model_name, device):
        import open_clip
        import torch
        self.torch = torch
        self.model, self.preprocess = open_clip.create_model_from_pretrained(model_name)
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.device = device
        self.model.eval().to(device)

    def encode_images(self, paths):
        from PIL import Image
        imgs = [self.preprocess(Image.open(p).convert("RGB")) for p in paths]
        batch = self.torch.stack(imgs).to(self.device)
        with self.torch.no_grad():
            feats = self.model.encode_image(batch)
        return feats.cpu().numpy()

    def encode_text(self, text):
        toks = self.tokenizer([text]).to(self.device)
        with self.torch.no_grad():
            feat = self.model.encode_text(toks)
        return feat.cpu().numpy()[0]


class VisualEmbedder:
    def __init__(self, model_name, device="cpu", backend=None):
        self.model_name = model_name
        self.device = device
        self._backend = backend

    @property
    def backend(self):
        if self._backend is None:
            self._backend = OpenClipBackend(self.model_name, resolve_device(self.device))
        return self._backend

    def embed_images(self, paths):
        paths = list(paths)
        if not paths:
            return np.zeros((0, 0), dtype="float32")
        return _l2_normalize(self.backend.encode_images(paths))

    def embed_query(self, text):
        vec = self.backend.encode_text(text)
        return _l2_normalize(np.asarray([vec], dtype="float32"))[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_visual_embed.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/visual_embed.py tests/test_visual_embed.py
git commit -m "feat: swappable local visual embedder (open_clip) with normalization"
```

---

### Task 3: Visual index (`engine/visual_index.py`)

**Files:**
- Create: `engine/visual_index.py`
- Test: `tests/test_visual_index.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_visual_index.py`:

```python
import numpy as np
import pytest

from engine.visual_index import build_visual_index, VisualIndex
from engine.index import Hit


class FakeVisualEmbedder:
    """Deterministic 2-D image vectors keyed by filename for predictable search."""
    def embed_images(self, paths):
        out = []
        for p in paths:
            out.append([1.0, 0.0] if "rhoton" in str(p).lower() else [0.0, 1.0])
        return np.array(out, dtype="float32")


def _pages():
    return [
        {"book": "Rhoton", "chapter": "Sellar", "page": 531,
         "figure_path": "/x/rhoton_p531.png", "caption": "Figure: cavernous sinus"},
        {"book": "Benzel", "chapter": "Fusion", "page": 20,
         "figure_path": "/x/benzel_p20.png", "caption": "Figure: pedicle screw"},
    ]


@pytest.mark.integration
def test_build_and_image_search(tmp_path):
    emb = FakeVisualEmbedder()
    build_visual_index(_pages(), emb, tmp_path / "idx")
    vidx = VisualIndex(tmp_path / "idx")

    hits = vidx.image_search([1.0, 0.0], k=2)  # closest to the "rhoton" vector
    assert isinstance(hits[0], Hit)
    assert hits[0].book == "Rhoton"
    assert hits[0].page == 531
    assert hits[0].figure_path == "/x/rhoton_p531.png"
    assert hits[0].has_figure is True
    assert "cavernous sinus" in hits[0].caption


@pytest.mark.integration
def test_missing_table_raises(tmp_path):
    with pytest.raises(Exception):
        VisualIndex(tmp_path / "empty")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_visual_index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.visual_index'`.

- [ ] **Step 3: Implement `engine/visual_index.py`**

```python
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
        rows = (self.tbl.search([float(x) for x in query_vector])
                .limit(k).to_list())
        return [
            Hit(id=r["id"], book=r["book"], chapter=r["chapter"] or None,
                page=int(r["page"]), text=r["caption"] or "",
                has_figure=True, caption=(r["caption"] or None),
                figure_path=r["figure_path"])
            for r in rows
        ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_visual_index.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/visual_index.py tests/test_visual_index.py
git commit -m "feat: visual index (figures table) build + image_search"
```

---

### Task 4: Appended figure sources in synthesis

**Files:**
- Modify: `engine/synthesize.py`
- Test: `tests/test_synthesize.py`

A figure surfaced only by the visual lane has `source_n > len(hits)`. Synthesis must render it as an extra numbered source and cite it. Existing behavior (all figures inline, `source_n <= len(hits)`) is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_synthesize.py`:

```python
class FullFakeFigure:
    def __init__(self, source_n, book, chapter, page, caption):
        self.source_n = source_n
        self.book = book
        self.chapter = chapter
        self.page = page
        self.caption = caption


def test_synthesize_appends_visual_only_figure_source():
    client = FakeSynthClient()
    hit = _hit()  # one passage -> len(hits) == 1
    fig = FullFakeFigure(source_n=2, book="Rhoton", chapter="Sellar", page=531,
                         caption="cavernous sinus plate")
    out = synthesize("cs?", [hit], figures=[fig], images=[b"PNG"],
                     synth_client=client)
    user = client.captured["user"]
    assert "Additional figure sources:" in user
    assert "[2] Rhoton, Sellar, p.531 (figure)" in user
    assert "cavernous sinus plate" in user
    # citations include the passage AND the appended figure source
    ns = [c.n for c in out.citations]
    assert ns == [1, 2]
    assert out.citations[1].book == "Rhoton"
    assert out.citations[1].page == 531
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_synthesize.py::test_synthesize_appends_visual_only_figure_source -v`
Expected: FAIL — no "Additional figure sources:" block and citations == [1].

- [ ] **Step 3: Implement the appended-source logic**

In `engine/synthesize.py`, add these two helpers after `_figure_note`:

```python
def _appended_figures(hits, figures):
    k = len(hits)
    return sorted((f for f in figures if f.source_n > k),
                  key=lambda f: f.source_n)


def _format_appended(appended):
    if not appended:
        return ""
    lines = []
    for f in appended:
        loc = f.book
        if f.chapter:
            loc += f", {f.chapter}"
        loc += f", p.{f.page}"
        cap = f": {f.caption}" if f.caption else ""
        lines.append(f"[{f.source_n}] {loc} (figure){cap}")
    return "\n\nAdditional figure sources:\n" + "\n".join(lines)
```

Replace the `synthesize` function body with:

```python
def synthesize(question, hits, figures, images, synth_client):
    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    answer = synth_client.generate(SYSTEM_PROMPT, user, images)
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    for f in appended:
        citations.append(Citation(n=f.source_n, book=f.book,
                                  chapter=f.chapter or "", page=f.page))
    return Synthesis(answer=answer, citations=citations)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_synthesize.py -v`
Expected: PASS (existing 3 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add engine/synthesize.py tests/test_synthesize.py
git commit -m "feat: render + cite visual-only figures as appended sources"
```

---

### Task 5: Fuse the visual lane into the query seam

**Files:**
- Modify: `engine/query.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Rewrite the query tests**

Replace the ENTIRE contents of `tests/test_query.py` with:

```python
# tests/test_query.py
from engine.query import Engine, QueryResult, Figure
from engine.index import Hit
from engine.synthesize import Synthesis, Citation


class FakeConfig:
    retrieve_k = 5
    rerank_k = 3
    max_figure_images = 3
    visual_retrieval = True
    visual_retrieve_k = 5


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0, 1.0]


class FakeIndex:
    def __init__(self, hits):
        self.hits = hits
        self.called_with = None

    def hybrid_search(self, query_text, query_vector, k):
        self.called_with = (query_text, query_vector, k)
        return self.hits


class FakeReranker:
    def rerank(self, query, hits, top_k):
        return hits[:top_k]


class FakeSynthClient:
    def __init__(self):
        self.captured = {}

    def generate(self, system, user, images):
        self.captured = {"images": images}
        return "answer"


class FakeVisualEmbedder:
    def embed_query(self, text):
        return [1.0, 0.0]


class FakeVisualIndex:
    def __init__(self, hits):
        self.hits = hits

    def image_search(self, query_vector, k):
        return self.hits


def capturing_synth(question, hits, figures, images, synth_client):
    synth_client.generate("sys", "user", images)
    return Synthesis(answer=f"ans:{len(hits)}:figs{len(figures)}",
                     citations=[Citation(1, "B", "C", 1)])


def _engine(cfg, index, synth, vemb=None, vidx=None):
    return Engine(cfg, FakeEmbedder(), index, FakeReranker(), synth_client=synth,
                  synth_fn=capturing_synth, visual_embedder=vemb, visual_index=vidx)


def test_engine_query_text_only():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]
    index = FakeIndex(hits)
    sc = FakeSynthClient()
    result = _engine(FakeConfig(), index, sc).query("normal icp?")
    assert isinstance(result, QueryResult)
    assert result.answer == "ans:2:figs0"
    assert index.called_with == ("normal icp?", [0.0, 1.0], 5)
    assert result.figures == []
    assert sc.captured["images"] == []


def test_engine_query_collects_text_figure(tmp_path):
    png = tmp_path / "p0012.png"
    png.write_bytes(b"PNGBYTES")
    hits = [
        Hit(id="a", book="Rhoton", chapter="Sellar", page=12, text="cs anatomy",
            has_figure=True, caption="Figure 12-1: cs", figure_path=str(png)),
        Hit(id="b", book="Greenberg", chapter="Tumors", page=40, text="text only"),
    ]
    sc = FakeSynthClient()
    result = _engine(FakeConfig(), FakeIndex(hits), sc).query("cavernous sinus?")
    assert len(result.figures) == 1
    fig = result.figures[0]
    assert isinstance(fig, Figure)
    assert fig.source_n == 1
    assert fig.book == "Rhoton"
    assert fig.image_path == str(png)
    assert sc.captured["images"] == [b"PNGBYTES"]


def test_visual_lane_appends_atlas_figure(tmp_path):
    # No text figure hits; visual lane finds an atlas plate on a page NOT in `top`.
    png = tmp_path / "rhoton_p531.png"
    png.write_bytes(b"ATLAS")
    top = [Hit(id="a", book="Greenberg", chapter="T", page=40, text="t1"),
           Hit(id="b", book="NeuroICU", chapter="P", page=10, text="t2")]
    visual = [Hit(id="v", book="Rhoton", chapter="Sellar", page=531,
                  text="cs", has_figure=True, caption="cavernous sinus",
                  figure_path=str(png))]
    sc = FakeSynthClient()
    eng = _engine(FakeConfig(), FakeIndex(top), sc,
                  vemb=FakeVisualEmbedder(), vidx=FakeVisualIndex(visual))
    result = eng.query("cavernous sinus plate?")
    assert len(result.figures) == 1
    fig = result.figures[0]
    assert fig.book == "Rhoton"
    assert fig.page == 531
    assert fig.source_n == 3  # appended after the 2 passages (len(top)+1)
    assert sc.captured["images"] == [b"ATLAS"]


def test_visual_lane_disabled_when_off(tmp_path):
    png = tmp_path / "rhoton_p531.png"
    png.write_bytes(b"ATLAS")
    top = [Hit(id="a", book="Greenberg", chapter="T", page=40, text="t1")]
    visual = [Hit(id="v", book="Rhoton", chapter="S", page=531, text="cs",
                  has_figure=True, caption="cs", figure_path=str(png))]

    class Off(FakeConfig):
        visual_retrieval = False

    sc = FakeSynthClient()
    eng = _engine(Off(), FakeIndex(top), sc,
                  vemb=FakeVisualEmbedder(), vidx=FakeVisualIndex(visual))
    result = eng.query("q")
    assert result.figures == []  # lane off -> no visual figures


def test_respects_cap_distinct_paths(tmp_path):
    hits = []
    for i in range(1, 4):
        png = tmp_path / f"p{i}.png"
        png.write_bytes(b"X")
        hits.append(Hit(id=str(i), book="Rhoton", chapter="C", page=i, text="t",
                        has_figure=True, caption="cap", figure_path=str(png)))

    class Cfg(FakeConfig):
        rerank_k = 5
        max_figure_images = 2

    sc = FakeSynthClient()
    result = _engine(Cfg(), FakeIndex(hits), sc).query("q")
    assert len(result.figures) == 2
    assert len(sc.captured["images"]) == 2


def test_drops_missing_figure_file(tmp_path):
    missing = tmp_path / "gone.png"
    hits = [Hit(id="a", book="Rhoton", chapter="C", page=12, text="cs",
                has_figure=True, caption="cap", figure_path=str(missing)),
            Hit(id="b", book="Greenberg", chapter="C", page=40, text="text only")]
    sc = FakeSynthClient()
    result = _engine(FakeConfig(), FakeIndex(hits), sc).query("q")
    assert result.figures == []
    assert sc.captured["images"] == []


def test_select_figures_no_synthesis(tmp_path):
    png = tmp_path / "p12.png"
    png.write_bytes(b"PNG")
    hits = [Hit(id="a", book="Rhoton", chapter="S", page=12, text="cs",
                has_figure=True, caption="cap", figure_path=str(png))]
    sc = FakeSynthClient()
    eng = _engine(FakeConfig(), FakeIndex(hits), sc)
    figs = eng.select_figures("q")
    assert len(figs) == 1 and figs[0].book == "Rhoton"
    assert sc.captured == {}  # synthesis never called
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_query.py -v`
Expected: FAIL — `Engine.__init__` has no `visual_embedder`/`visual_index`, no `select_figures`.

- [ ] **Step 3: Rewrite `engine/query.py`**

Replace the ENTIRE contents of `engine/query.py` with:

```python
from dataclasses import dataclass, field

from .config import load_config
from .embed import Embedder
from .index import Index, reciprocal_rank_fusion
from .rerank import Reranker
from .synthesize import synthesize
from .synth_clients import make_synth_client
from .visual_embed import VisualEmbedder
from .visual_index import VisualIndex


@dataclass
class Figure:
    source_n: int
    book: str
    chapter: str
    page: int
    image_path: str
    caption: str


@dataclass
class QueryResult:
    answer: str
    citations: list = field(default_factory=list)
    figures: list = field(default_factory=list)


class Engine:
    def __init__(self, config, embedder, index, reranker, synth_client,
                 synth_fn=synthesize, visual_embedder=None, visual_index=None):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.synth_client = synth_client
        self.synth_fn = synth_fn
        self.visual_embedder = visual_embedder
        self.visual_index = visual_index

    def _visual_hits(self, question):
        if not (self.config.visual_retrieval and self.visual_embedder is not None
                and self.visual_index is not None):
            return []
        qv = self.visual_embedder.embed_query(question)
        return self.visual_index.image_search(qv, self.config.visual_retrieve_k)

    def _collect_figures(self, question, top):
        """Return aligned (figures, images): RRF-fuse figure-bearing text hits with
        visual-lane hits (keyed by figure_path), dedupe, cap, assign citation source
        numbers (reuse a passage number if the page is cited, else append), and read
        bytes (dropping unreadable PNGs from BOTH lists)."""
        text_fig = [h for h in top if h.has_figure and h.figure_path]
        visual = self._visual_hits(question)

        by_path = {}
        for h in visual:        # text metadata wins on overlap
            if h.figure_path:
                by_path[h.figure_path] = h
        for h in text_fig:
            if h.figure_path:
                by_path[h.figure_path] = h

        fused = reciprocal_rank_fusion([[h.figure_path for h in text_fig],
                                        [h.figure_path for h in visual]])

        passage_index = {}
        for i, h in enumerate(top, 1):
            passage_index.setdefault((h.book, h.page), i)

        figures, images = [], []
        next_appended = len(top) + 1
        for path, _score in fused:
            if len(figures) >= self.config.max_figure_images:
                break
            h = by_path.get(path)
            if h is None:
                continue
            image = self._read_image(path)
            if image is None:
                continue
            src = passage_index.get((h.book, h.page))
            if src is None:
                src = next_appended
                next_appended += 1
            figures.append(Figure(source_n=src, book=h.book,
                                  chapter=h.chapter or "", page=h.page,
                                  image_path=path, caption=h.caption or ""))
            images.append(image)
        return figures, images

    @staticmethod
    def _read_image(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def _retrieve(self, question):
        qv = self.embedder.embed_query(question)
        hits = self.index.hybrid_search(question, qv, self.config.retrieve_k)
        return self.reranker.rerank(question, hits, self.config.rerank_k)

    def select_figures(self, question):
        """Figures the system would attach, without calling synthesis (for eval)."""
        figures, _ = self._collect_figures(question, self._retrieve(question))
        return figures

    def query(self, question):
        top = self._retrieve(question)
        figures, images = self._collect_figures(question, top)
        syn = self.synth_fn(question, top, figures, images, self.synth_client)
        return QueryResult(answer=syn.answer, citations=syn.citations,
                           figures=figures)


_engine = None


def get_engine(config=None):
    global _engine
    if _engine is not None:
        return _engine
    config = config or load_config()
    embedder = Embedder(config.embed_model, device=config.embed_device)
    index = Index(config.index_dir)
    reranker = Reranker(config.rerank_model, device=config.embed_device)
    synth_client = make_synth_client(config)
    visual_embedder = None
    visual_index = None
    if config.visual_retrieval:
        try:
            visual_index = VisualIndex(config.index_dir)
            visual_embedder = VisualEmbedder(config.visual_model,
                                             device=config.embed_device)
        except Exception:
            visual_index = None
            visual_embedder = None
    _engine = Engine(config, embedder, index, reranker, synth_client,
                     visual_embedder=visual_embedder, visual_index=visual_index)
    return _engine


def query(question, config=None):
    return get_engine(config).query(question)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_query.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add engine/query.py tests/test_query.py
git commit -m "feat: RRF-fuse visual lane into figure selection at the query seam"
```

---

### Task 6: Build scripts for the visual index

**Files:**
- Create: `scripts/build_visual_index.py`
- Modify: `scripts/build_index.py`

- [ ] **Step 1: Create the standalone builder `scripts/build_visual_index.py`**

```python
import time

import lancedb

from engine.config import load_config, resolve_device
from engine.visual_embed import VisualEmbedder
from engine.visual_index import build_visual_index


def figure_pages_from_chunks(index_dir):
    """Distinct figure pages (deduped by figure_path) read from the existing
    `chunks` table, so we reuse the PNGs rendered during the text-index build."""
    tbl = lancedb.connect(str(index_dir)).open_table("chunks")
    t = tbl.to_arrow()
    cols = {c: t.column(c).to_pylist()
            for c in ("book", "chapter", "page", "has_figure", "figure_path",
                      "caption")}
    seen = {}
    for b, ch, p, hf, fp, cap in zip(cols["book"], cols["chapter"], cols["page"],
                                     cols["has_figure"], cols["figure_path"],
                                     cols["caption"]):
        if hf and fp and fp not in seen:
            seen[fp] = {"book": b, "chapter": ch or None, "page": p,
                        "figure_path": fp, "caption": cap or None}
    return list(seen.values())


def main():
    cfg = load_config()
    pages = figure_pages_from_chunks(cfg.index_dir)
    print(f"{len(pages)} distinct figure pages to embed")
    device = resolve_device(cfg.embed_device)
    print(f"Loading visual model '{cfg.visual_model}' on '{device}' "
          f"(first run downloads weights) ...", flush=True)
    embedder = VisualEmbedder(cfg.visual_model, device=device)

    def progress(done, total):
        print(f"    embedded {done}/{total} figure images", flush=True)

    t0 = time.time()
    build_visual_index(pages, embedder, cfg.index_dir, on_progress=progress)
    print(f"\nVisual index built at {cfg.index_dir} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the standalone script imports**

Run: `python3 -c "import scripts.build_visual_index"`
Expected: imports cleanly.

- [ ] **Step 3: Wire the visual index into `scripts/build_index.py`**

In `scripts/build_index.py`, add imports near the top (next to the other engine imports):

```python
from engine.visual_embed import VisualEmbedder
from engine.visual_index import build_visual_index
```

At the END of `main()`, after the `print(f"\nIndex built at {cfg.index_dir} ...")` line, append:

```python
    if cfg.visual_retrieval:
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
```

- [ ] **Step 4: Smoke-test the build script wiring**

Run: `python3 -c "import scripts.build_index"`
Expected: imports cleanly.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_visual_index.py scripts/build_index.py
git commit -m "feat: build visual index (standalone over cached PNGs + in full build)"
```

---

### Task 7: Evaluate the fused figure selection

**Files:**
- Modify: `eval/figure_eval.py`

The current gate inspects raw text hybrid hits, which ignores the visual lane. Switch it to evaluate `engine.select_figures(...)` — the figures the system actually attaches.

- [ ] **Step 1: Rewrite the case loop in `eval/figure_eval.py`**

Replace the body of the `for case in cases:` loop (everything from `q = case["question"]` down to the end of the `if args.synthesize:` block) with:

```python
        q = case["question"]
        figs = engine.select_figures(q)
        want_book = case["expect_book_contains"].lower()
        want_page = case.get("expect_page")
        matches = [f for f in figs
                   if want_book in f.book.lower()
                   and (want_page is None or f.page == want_page)]
        ok = len(matches) > 0
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"    figures attached: {[(f.book, f.page) for f in figs]}")
        if args.synthesize:
            result = engine.query(q)
            print(f"    answer: {result.answer[:600]}")
            print(f"    figures shown: "
                  f"{[(fg.book, fg.page) for fg in result.figures]}\n")
```

(The summary line `print(f"\nFigure-retrieval gate: {passed}/{len(cases)} passed")` after the loop stays as-is.)

- [ ] **Step 2: Smoke-test wiring**

Run: `python3 -m py_compile eval/figure_eval.py`
Expected: compiles cleanly.

Run: `python3 -m pytest -q`
Expected: full unit suite still green (eval is not unit-tested, but confirm no import regressions elsewhere).

- [ ] **Step 3: Commit**

```bash
git add eval/figure_eval.py
git commit -m "feat: figure gate evaluates the fused (text+visual) figure selection"
```

---

### Task 8: Full verification, live gates, and README

**Files:**
- Modify: `README.md`

No new tests; this runs everything and documents Phase 2b. The visual-index build and the live gates need the real corpus + GPU + Vertex auth, so the steps below are the human-run validation.

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest -q`
Expected: all Phase 1/2a/2b unit + integration tests PASS.

- [ ] **Step 2: Build the visual index (fast path — reuses cached PNGs)**

Run: `python3 -m scripts.build_visual_index`
Expected: prints "N distinct figure pages to embed", downloads the visual model on first run, embeds, and writes the `figures` table to `INDEX_DIR`. N should match the total figure pages reported by the Phase 2a build.

- [ ] **Step 3: A/B the lane on the figure gate**

```bash
VISUAL_RETRIEVAL=off python3 -m eval.figure_eval   # Phase 2a baseline (was 3/5)
python3 -m eval.figure_eval                          # with visual lane
```

Expected: the two atlas misses (Fukushima petroclival/Meckel's, neurovascular giant-ICA aneurysm) now attach atlas plates with the lane on. If recall doesn't improve, try the model bake-off (Step 4) before concluding.

- [ ] **Step 4: Model bake-off**

```bash
VISUAL_MODEL='hf-hub:timm/ViT-SO400M-14-SigLIP-384' python3 -m scripts.build_visual_index
VISUAL_MODEL='hf-hub:timm/ViT-SO400M-14-SigLIP-384' python3 -m eval.figure_eval
```

Compare against the BiomedCLIP run from Step 3. Keep whichever scores better in `.env` (`VISUAL_MODEL=`). Update `eval/figure_answers.yaml` expectations to the genuinely-correct source(s) per query if needed — encode reality, do NOT edit them just to turn the gate green.

- [ ] **Step 5: Blinded synthesis review (go/no-go)**

Run: `python3 -m eval.figure_eval --synthesize`
Expected: for each case, a cited answer + the attached figures. Hand the surfaced atlas plates to an independent reviewer (the neurosurgeon-agent pattern): are these the right figures, and does the answer faithfully describe them? This is the merge go/no-go.

- [ ] **Step 6: Update README**

Add a "Phase 2b — visual retrieval" subsection to `README.md` covering: the new `.env` keys (`VISUAL_MODEL`, `VISUAL_RETRIEVE_K`, `VISUAL_RETRIEVAL`), the `open_clip_torch` dep, that only `python3 -m scripts.build_visual_index` is needed (no full re-index), the A/B + model bake-off commands, and the known limitations (whole-page embedding; general/biomedical CLIP imperfect on line-drawings; per-figure crop is the documented next fallback). Also update the `## Roadmap` so Phase 2b moves from "deferred" to "implemented", and add the Phase 2b spec/plan to the Design docs list.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: Phase 2b visual retrieval — setup, A/B + bake-off, limitations"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** local swappable embedder (T1/T2), `figures` table build + reuse of cached PNGs (T3/T6), CLIP text-tower query + image_search (T2/T3), RRF figure fusion keyed by path (T5), citation reuse-or-append (T4/T5), graceful fallback when table absent / lane off (T5 `get_engine` try/except + `visual_retrieval` guard, tested), config knobs (T1), A/B + bake-off + blinded gates (T7/T8), no-full-reindex standalone builder (T6). All spec sections map to a task.
- **Type consistency:** `VisualIndex.image_search` returns `engine.index.Hit` (same type the text lane uses), so `_collect_figures` treats both lanes uniformly. `Figure(source_n, book, chapter, page, image_path, caption)` is unchanged from Phase 2a; `synthesize` reads `f.source_n/.book/.chapter/.page/.caption` on appended figures (all present on `Figure`). `reciprocal_rank_fusion` is imported from `engine.index` and fed `figure_path` id-lists. `embed_images`/`embed_query`/`image_search`/`build_visual_index` signatures match across Tasks 2, 3, 5, 6.
- **Backward compatibility:** Phase 2a query/synthesize behavior is preserved when no visual lane is wired (existing-style tests pass); `_collect_figures` over text-only RRF reproduces the prior ordering and inline source numbers.
