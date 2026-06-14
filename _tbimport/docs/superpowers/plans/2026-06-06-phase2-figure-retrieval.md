# Phase 2 — Visual / Figure Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make anatomy/imaging questions answerable by surfacing the relevant textbook page image AND letting a vision model read it, returning a cited answer plus the figure.

**Architecture:** Approach A — extend the Phase 1 text RAG. At ingest, detect figure-bearing pages and render them to cached PNGs; carry `has_figure`/`caption`/`figure_path` from page → chunk → LanceDB → `Hit`. At query time, reuse existing hybrid retrieval + rerank, attach the top figure-bearing page images to a multimodal Gemini call (Vertex AI, with OpenRouter as a config fallback), and return a `figures[]` field through the existing `query()` seam. A minimal Streamlit page displays answer + figures.

**Tech Stack:** Python, PyMuPDF (`fitz`), LanceDB, sentence-transformers (BGE), google-genai (Vertex), openai (OpenRouter fallback), Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-06-06-neuro-textbook-rag-phase2-figure-retrieval-design.md`

**Conventions from Phase 1 to follow:**
- Dependency injection for testability: heavy clients/models are injectable (`Embedder(encoder=...)`, `Reranker(scorer=...)`, synth client). Real network/model calls are NOT unit-tested; they are covered by the eval gates.
- New dataclass fields are added with defaults so existing keyword construction keeps working.
- LanceDB round-trip is covered by a `@pytest.mark.integration` test.
- Commit after each task.

**Note on google-genai:** The Vertex adapter (Task 7) targets `google-genai >= 1.0` (`from google import genai`; `genai.Client(vertexai=True, ...)`; `client.models.generate_content(...)`; `types.Part.from_bytes`). If the installed SDK import shape differs, check `pip show google-genai` before adapting — do not change the tested message-shaping logic, only the adapter's call into the SDK.

---

### Task 1: Dependencies and configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `engine/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add the failing config test**

Append to `tests/test_config.py`:

```python
def test_phase2_defaults_present(tmp_path, monkeypatch):
    # No env file, no overrides -> Phase 2 defaults resolve.
    monkeypatch.delenv("SYNTH_PROVIDER", raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.synth_provider == "vertex"
    assert cfg.google_cloud_location == "us-central1"
    assert cfg.vertex_model  # non-empty Flash-tier default
    assert cfg.max_figure_images == 3
    assert cfg.figure_dpi == 160
    assert abs(cfg.figure_area_threshold - 0.1) < 1e-9
    assert str(cfg.assets_dir).endswith("assets/figures")


def test_env_overrides_synth_provider(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SYNTH_PROVIDER=openrouter\nMAX_FIGURE_IMAGES=1\n")
    cfg = load_config(env_file=str(env))
    assert cfg.synth_provider == "openrouter"
    assert cfg.max_figure_images == 1
```

If `tests/test_config.py` does not already import `load_config`, add at the top: `from engine.config import load_config`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_config.py::test_phase2_defaults_present -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'synth_provider'`.

- [ ] **Step 3: Add the new config fields**

In `engine/config.py`, add to `DEFAULTS` (keep existing entries):

```python
    "SYNTH_PROVIDER": "vertex",
    "GOOGLE_CLOUD_PROJECT": "",
    "GOOGLE_CLOUD_LOCATION": "us-central1",
    "VERTEX_MODEL": "gemini-2.5-flash",
    "MAX_FIGURE_IMAGES": "3",
    "FIGURE_DPI": "160",
    "FIGURE_AREA_THRESHOLD": "0.1",
    "ASSETS_DIR": str(Path.home() / "neuro-textbook-rag" / "assets" / "figures"),
```

Add to the `Config` dataclass fields:

```python
    synth_provider: str
    google_cloud_project: str
    google_cloud_location: str
    vertex_model: str
    max_figure_images: int
    figure_dpi: int
    figure_area_threshold: float
    assets_dir: Path
```

Add to the `Config(...)` construction in `load_config`:

```python
        synth_provider=get("SYNTH_PROVIDER"),
        google_cloud_project=get("GOOGLE_CLOUD_PROJECT"),
        google_cloud_location=get("GOOGLE_CLOUD_LOCATION"),
        vertex_model=get("VERTEX_MODEL"),
        max_figure_images=int(get("MAX_FIGURE_IMAGES")),
        figure_dpi=int(get("FIGURE_DPI")),
        figure_area_threshold=float(get("FIGURE_AREA_THRESHOLD")),
        assets_dir=Path(get("ASSETS_DIR")),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Update requirements and .env.example**

Append to `requirements.txt`:

```
google-genai>=1.0
streamlit>=1.36
```

Append to `.env.example`:

```
# Phase 2 — figure retrieval / vision synthesis
SYNTH_PROVIDER=vertex
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
VERTEX_MODEL=gemini-2.5-flash
MAX_FIGURE_IMAGES=3
FIGURE_DPI=160
FIGURE_AREA_THRESHOLD=0.1
ASSETS_DIR=/home/michael/neuro-textbook-rag/assets/figures
```

- [ ] **Step 6: Install new deps**

Run: `pip install -r requirements.txt`
Expected: `google-genai` and `streamlit` install without error.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt engine/config.py .env.example tests/test_config.py
git commit -m "feat: Phase 2 config (vertex provider, figure knobs) and deps"
```

---

### Task 2: Figure detection, caption, and page rendering (`engine/figures.py`)

**Files:**
- Create: `engine/figures.py`
- Modify: `tests/conftest.py` (add a figure-bearing PDF fixture)
- Test: `tests/test_figures.py`

- [ ] **Step 1: Add the `pdf_with_figure` fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def pdf_with_figure(tmp_path):
    """2-page PDF 'Atlas Book.pdf': page 1 has a large image + a caption line;
    page 2 is text-only."""
    path = tmp_path / "Atlas Book.pdf"
    doc = fitz.open()
    p1 = doc.new_page()  # default A4 595x842 pts
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 400))
    pix.clear_with(200)  # fill gray so it's a real raster image
    p1.insert_image(fitz.Rect(50, 50, 550, 550), pixmap=pix)  # ~0.5 of page area
    p1.insert_text((50, 700), "Figure 1-1: Lateral view of the cavernous sinus")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Page 2 plain clinical text without imagery")
    doc.save(path)
    doc.close()
    return path
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_figures.py`:

```python
import fitz

from engine.figures import (
    figure_area_fraction, detect_figure, extract_caption,
    page_figure_info, render_page_png,
)


def test_detect_figure_true_on_image_page(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    assert figure_area_fraction(doc[0]) > 0.3
    assert detect_figure(doc[0], area_threshold=0.1) is True
    doc.close()


def test_detect_figure_false_on_text_page(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    assert figure_area_fraction(doc[1]) == 0.0
    assert detect_figure(doc[1], area_threshold=0.1) is False
    doc.close()


def test_extract_caption(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    assert extract_caption(doc[0]) == "Figure 1-1: Lateral view of the cavernous sinus"
    assert extract_caption(doc[1]) is None
    doc.close()


def test_page_figure_info(pdf_with_figure):
    doc = fitz.open(pdf_with_figure)
    info = page_figure_info(doc[0], area_threshold=0.1)
    assert info.has_figure is True
    assert "cavernous sinus" in info.caption
    info2 = page_figure_info(doc[1], area_threshold=0.1)
    assert info2.has_figure is False
    assert info2.caption is None
    doc.close()


def test_render_page_png_creates_and_is_idempotent(pdf_with_figure, tmp_path):
    doc = fitz.open(pdf_with_figure)
    out = tmp_path / "figs" / "Atlas Book" / "p0001.png"
    p = render_page_png(doc[0], dpi=120, out_path=out)
    assert p.exists() and p.stat().st_size > 0
    mtime = p.stat().st_mtime_ns
    # second call must NOT re-render (resumable behavior)
    render_page_png(doc[0], dpi=120, out_path=out)
    assert p.stat().st_mtime_ns == mtime
    doc.close()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_figures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.figures'`.

- [ ] **Step 4: Implement `engine/figures.py`**

```python
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Lines that begin a figure caption: "Figure 1-1: ...", "Fig. 3 ...", "Plate 5 ..."
CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|plate)\b[\s.:]*\S", re.IGNORECASE)


@dataclass
class FigureInfo:
    has_figure: bool
    caption: Optional[str]


def figure_area_fraction(page):
    """Fraction of the page covered by embedded raster images (0.0–~1.0)."""
    page_area = abs(page.rect.width * page.rect.height)
    if page_area == 0:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        bbox = info.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        covered += abs((x1 - x0) * (y1 - y0))
    return covered / page_area


def detect_figure(page, area_threshold):
    return figure_area_fraction(page) >= area_threshold


def extract_caption(page):
    for line in page.get_text().splitlines():
        if CAPTION_RE.match(line):
            return line.strip()
    return None


def page_figure_info(page, area_threshold):
    if detect_figure(page, area_threshold):
        return FigureInfo(has_figure=True, caption=extract_caption(page))
    return FigureInfo(has_figure=False, caption=None)


def render_page_png(page, dpi, out_path):
    """Render a page to PNG at the given DPI. Skips if the file already exists
    (so a re-run does not re-render — the rendering pass is crash-resumable)."""
    out_path = Path(out_path)
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(dpi=dpi)
    pix.save(str(out_path))
    return out_path
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_figures.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add engine/figures.py tests/test_figures.py tests/conftest.py
git commit -m "feat: figure detection, caption extraction, page rendering"
```

---

### Task 3: Wire figure detection into ingest

**Files:**
- Modify: `engine/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ingest.py`:

```python
def test_extract_pages_sets_figure_fields(pdf_with_figure):
    recs = extract_pages(pdf_with_figure, area_threshold=0.1)
    assert recs[0].has_figure is True
    assert "cavernous sinus" in recs[0].caption
    assert recs[0].figure_path is None  # render=False by default
    assert recs[1].has_figure is False
    assert recs[1].caption is None


def test_extract_pages_renders_when_requested(pdf_with_figure, tmp_path):
    recs = extract_pages(pdf_with_figure, render=True, assets_dir=tmp_path,
                         dpi=120, area_threshold=0.1)
    assert recs[0].figure_path is not None
    from pathlib import Path
    assert Path(recs[0].figure_path).exists()
    assert recs[1].figure_path is None


def test_coverage_includes_figure_counts(pdf_with_figure):
    rep = coverage_report(pdf_with_figure.parent)
    assert rep["Atlas Book"]["pages_with_figures"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_ingest.py -k figure -v`
Expected: FAIL — `PageRecord` has no `has_figure`, and `extract_pages` rejects `area_threshold`.

- [ ] **Step 3: Extend `PageRecord` and `extract_pages`**

In `engine/ingest.py`, add imports near the top:

```python
from engine.figures import page_figure_info, render_page_png
```

Extend the `PageRecord` dataclass (add fields after `chapter`):

```python
    has_figure: bool = False
    caption: Optional[str] = None
    figure_path: Optional[str] = None
```

Replace `extract_pages` with:

```python
def extract_pages(pdf_path, render=False, assets_dir=None, dpi=160,
                  area_threshold=0.1):
    pdf_path = Path(pdf_path)
    book = pdf_path.stem
    doc = fitz.open(pdf_path)
    entries = _chapter_entries(doc)
    records = []
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text().strip()
        pageno = i + 1
        info = page_figure_info(page, area_threshold)
        figure_path = None
        if info.has_figure and render and assets_dir is not None:
            out = Path(assets_dir) / book / f"p{pageno:04d}.png"
            render_page_png(page, dpi, out)
            figure_path = str(out)
        records.append(
            PageRecord(book=book, page=pageno, text=text,
                       chapter=_chapter_for_page(entries, pageno),
                       has_figure=info.has_figure, caption=info.caption,
                       figure_path=figure_path)
        )
    doc.close()
    return records
```

In `coverage_from_records`, add a key inside the per-book `report[book]` dict:

```python
            "pages_with_figures": sum(1 for r in recs if r.has_figure),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_ingest.py -v`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add engine/ingest.py tests/test_ingest.py
git commit -m "feat: detect figures during ingest; render pages; figure coverage"
```

---

### Task 4: Propagate figure attributes through chunking

**Files:**
- Modify: `engine/chunk.py`
- Test: `tests/test_chunk.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_chunk.py`:

```python
def test_chunks_carry_figure_attrs():
    rec = PageRecord(book="B", page=3, text="alpha beta", chapter="C",
                     has_figure=True, caption="Figure 3-1: x", figure_path="/p3.png")
    chunks = chunk_page(rec, max_words=600, overlap=80)
    assert chunks[0].has_figure is True
    assert chunks[0].caption == "Figure 3-1: x"
    assert chunks[0].figure_path == "/p3.png"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_chunk.py::test_chunks_carry_figure_attrs -v`
Expected: FAIL — `Chunk` has no `has_figure`.

- [ ] **Step 3: Extend `Chunk` and `chunk_page`**

In `engine/chunk.py`, add fields to the `Chunk` dataclass (after `text`):

```python
    has_figure: bool = False
    caption: Optional[str] = None
    figure_path: Optional[str] = None
```

In `chunk_page`, replace the `chunks.append(Chunk(...))` call with:

```python
        chunks.append(Chunk(
            id=f"{record.book}::p{record.page}::{idx}",
            book=record.book,
            chapter=record.chapter,
            page=record.page,
            text=text,
            has_figure=record.has_figure,
            caption=record.caption,
            figure_path=record.figure_path,
        ))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_chunk.py -v`
Expected: PASS (existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add engine/chunk.py tests/test_chunk.py
git commit -m "feat: carry figure attrs from page records into chunks"
```

---

### Task 5: Persist and retrieve figure columns in LanceDB

**Files:**
- Modify: `engine/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_index.py`:

```python
@pytest.mark.integration
def test_figure_columns_round_trip(tmp_path):
    chunks = [
        Chunk(id="a::p1::0", book="Rhoton", chapter="Sellar", page=12,
              text="cavernous sinus anatomy lateral view", has_figure=True,
              caption="Figure 12-1: cavernous sinus", figure_path="/x/p0012.png"),
        Chunk(id="b::p2::0", book="Greenberg", chapter="Tumors", page=40,
              text="meningioma grading text only"),
    ]
    emb = FakeEmbedder()
    build_index(chunks, emb, tmp_path / "idx")
    idx = Index(tmp_path / "idx")
    hits = idx.hybrid_search("cavernous sinus", emb.embed_query("spine"), k=2)
    by_book = {h.book: h for h in hits}
    assert by_book["Rhoton"].has_figure is True
    assert by_book["Rhoton"].figure_path == "/x/p0012.png"
    assert "cavernous sinus" in by_book["Rhoton"].caption
    assert by_book["Greenberg"].has_figure is False
    assert by_book["Greenberg"].figure_path is None
```

(Note: `FakeEmbedder.embed_texts` maps any non-"icp" text to `[0.0, 1.0]`; both chunks map there, which is fine — the test asserts on round-tripped columns, not ranking.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_index.py::test_figure_columns_round_trip -v -m integration`
Expected: FAIL — `Hit` has no `has_figure` / columns absent.

- [ ] **Step 3: Extend the schema and `Hit`**

In `engine/index.py`, add fields to the `Hit` dataclass (after `score`):

```python
    has_figure: bool = False
    caption: Optional[str] = None
    figure_path: Optional[str] = None
```

In `build_index`, extend the appended row dict (add keys alongside existing ones):

```python
            "has_figure": bool(c.has_figure),
            "caption": c.caption or "",
            "figure_path": c.figure_path or "",
```

In `Index._row_to_hit`, extend the returned `Hit(...)`:

```python
        return Hit(
            id=row["id"], book=row["book"],
            chapter=row["chapter"] or None, page=int(row["page"]),
            text=row["text"],
            has_figure=bool(row.get("has_figure", False)),
            caption=(row.get("caption") or None),
            figure_path=(row.get("figure_path") or None),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_index.py -v`
Expected: PASS (existing + new integration test).

- [ ] **Step 5: Commit**

```bash
git add engine/index.py tests/test_index.py
git commit -m "feat: persist + return figure columns (has_figure, caption, figure_path)"
```

---

### Task 6: Multimodal synthesis (provider-agnostic)

**Files:**
- Modify: `engine/synthesize.py`
- Test: `tests/test_synthesize.py`

This changes `synthesize`'s signature to `synthesize(question, hits, figures, images, synth_client)` where `synth_client` exposes `generate(system, user, images) -> str`. The model id now lives inside the client (set up in Task 7). Phase 1's nested `client.chat.completions.create` mock is replaced by a simpler `FakeSynthClient`.

- [ ] **Step 1: Rewrite the synthesis tests**

Replace the entire contents of `tests/test_synthesize.py` with:

```python
# tests/test_synthesize.py
from engine.synthesize import synthesize, SYSTEM_PROMPT, _format_passages
from engine.index import Hit


class FakeSynthClient:
    def __init__(self):
        self.captured = {}

    def generate(self, system, user, images):
        self.captured = {"system": system, "user": user, "images": images}
        return "ICP is 5-15 mmHg [1]."


class FakeFigure:
    def __init__(self, source_n, book, page):
        self.source_n = source_n
        self.book = book
        self.page = page


def _hit():
    return Hit(id="x", book="NeuroICU", chapter="Pressure", page=10,
               text="normal icp is 5 to 15 mmHg")


def test_synthesize_builds_prompt_and_citations():
    client = FakeSynthClient()
    out = synthesize("normal icp?", [_hit()], figures=[], images=[],
                     synth_client=client)
    assert out.answer == "ICP is 5-15 mmHg [1]."
    assert client.captured["system"] == SYSTEM_PROMPT
    assert "[1] NeuroICU, Pressure, p.10" in client.captured["user"]
    assert "normal icp is 5 to 15 mmHg" in client.captured["user"]
    assert client.captured["images"] == []
    assert len(out.citations) == 1
    assert out.citations[0].n == 1
    assert out.citations[0].book == "NeuroICU"
    assert out.citations[0].page == 10


def test_synthesize_passes_images_and_figure_refs():
    client = FakeSynthClient()
    figs = [FakeFigure(source_n=1, book="Rhoton", page=12)]
    out = synthesize("cavernous sinus?", [_hit()], figures=figs,
                     images=[b"PNGDATA"], synth_client=client)
    assert client.captured["images"] == [b"PNGDATA"]
    assert "[1] Rhoton, p.12" in client.captured["user"]
    assert "Attached page images" in client.captured["user"]


def test_synthesize_no_hits_is_empty_refusal_path():
    assert _format_passages([]) == ""
    client = FakeSynthClient()
    out = synthesize("obscure?", [], figures=[], images=[], synth_client=client)
    assert out.citations == []
    assert client.captured["user"].rstrip().endswith("Passages:")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_synthesize.py -v`
Expected: FAIL — `synthesize` still has the old signature.

- [ ] **Step 3: Rewrite `engine/synthesize.py`**

```python
from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are a neurosurgical reference assistant. Answer ONLY from the provided "
    "textbook passages and any attached page images. Rules:\n"
    "- Cite the bracketed source number for every clinical claim, e.g. [2].\n"
    "- Some sources include an attached page image (a figure/plate). When an image "
    "is attached for a source, you may describe what the figure shows and must "
    "still cite that source number. Do not describe images that are not attached.\n"
    "- If the passages/images do not contain the answer, say "
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


def _figure_note(figures):
    if not figures:
        return ""
    refs = ", ".join(f"[{f.source_n}] {f.book}, p.{f.page}" for f in figures)
    return ("\n\nAttached page images (in order) correspond to these sources: "
            f"{refs}. Use them to describe the relevant figure and cite the source.")


def synthesize(question, hits, figures, images, synth_client):
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    user += _figure_note(figures)
    answer = synth_client.generate(SYSTEM_PROMPT, user, images)
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    return Synthesis(answer=answer, citations=citations)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_synthesize.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/synthesize.py tests/test_synthesize.py
git commit -m "feat: multimodal synthesis via provider-agnostic synth client"
```

---

### Task 7: Provider clients (Vertex + OpenRouter adapters)

**Files:**
- Create: `engine/synth_clients.py`
- Test: `tests/test_synth_clients.py`

Both adapters expose `generate(system, user, images) -> str` and accept an injectable underlying SDK client for testing (mirrors `Embedder(encoder=...)`). The OpenRouter adapter's base64 image-shaping is unit-tested; the live Vertex/OpenRouter network paths are covered by the figure-synthesis gate (Task 12), not unit tests.

- [ ] **Step 1: Write the failing test (OpenRouter shaping)**

Create `tests/test_synth_clients.py`:

```python
import base64

from engine.synth_clients import OpenRouterSynthClient, make_synth_client


class _FakeCompletions:
    def __init__(self, parent):
        self.parent = parent

    def create(self, model, messages, temperature):
        self.parent.captured = {"model": model, "messages": messages,
                                "temperature": temperature}

        class _M:
            content = "answer text"

        class _C:
            message = _M()

        class _R:
            choices = [_C()]

        return _R()


class FakeOpenAI:
    def __init__(self):
        self.captured = {}
        self.chat = self
        self.completions = _FakeCompletions(self)


def test_openrouter_text_only():
    fake = FakeOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="m", client=fake)
    out = c.generate("SYS", "USER", images=[])
    assert out == "answer text"
    msgs = fake.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1]["content"] == [{"type": "text", "text": "USER"}]


def test_openrouter_attaches_images_as_data_urls():
    fake = FakeOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="m", client=fake)
    c.generate("SYS", "USER", images=[b"PNGBYTES"])
    content = fake.captured["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "USER"}
    b64 = base64.b64encode(b"PNGBYTES").decode("ascii")
    assert content[1] == {"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}}


def test_make_synth_client_selects_provider():
    class Cfg:
        synth_provider = "openrouter"
        openrouter_api_key = "k"
        openrouter_model = "m"
        google_cloud_project = "p"
        google_cloud_location = "us-central1"
        vertex_model = "gemini-2.5-flash"

    c = make_synth_client(Cfg())
    assert isinstance(c, OpenRouterSynthClient)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_synth_clients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.synth_clients'`.

- [ ] **Step 3: Implement `engine/synth_clients.py`**

```python
import base64


class OpenRouterSynthClient:
    """OpenAI-compatible (OpenRouter) backend. Fallback when GCP credit runs out."""

    def __init__(self, api_key, model, client=None):
        self.api_key = api_key
        self.model = model
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url="https://openrouter.ai/api/v1",
                                  api_key=self.api_key)
        return self._client

    def generate(self, system, user, images):
        content = [{"type": "text", "text": user}]
        for img in images:
            b64 = base64.b64encode(img).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        return resp.choices[0].message.content


class VertexSynthClient:
    """Vertex AI Gemini backend (default). Spends the GCP credit.
    Auth via Application Default Credentials (gcloud auth application-default login).
    Targets google-genai >= 1.0."""

    def __init__(self, project, location, model, client=None):
        self.project = project
        self.location = location
        self.model = model
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(vertexai=True, project=self.project,
                                        location=self.location)
        return self._client

    def generate(self, system, user, images):
        from google.genai import types
        parts = [types.Part.from_text(text=user)]
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        resp = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0.1),
        )
        return resp.text


def make_synth_client(config):
    if config.synth_provider == "openrouter":
        return OpenRouterSynthClient(config.openrouter_api_key,
                                     config.openrouter_model)
    return VertexSynthClient(config.google_cloud_project,
                             config.google_cloud_location,
                             config.vertex_model)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_synth_clients.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/synth_clients.py tests/test_synth_clients.py
git commit -m "feat: Vertex + OpenRouter synth client adapters with provider select"
```

---

### Task 8: Wire figures through the query seam

**Files:**
- Modify: `engine/query.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Rewrite the query tests**

Replace the entire contents of `tests/test_query.py` with:

```python
# tests/test_query.py
from engine.query import Engine, QueryResult, Figure
from engine.index import Hit
from engine.synthesize import Synthesis, Citation


class FakeConfig:
    retrieve_k = 5
    rerank_k = 2
    max_figure_images = 3


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


def capturing_synth(question, hits, figures, images, synth_client):
    synth_client.generate("sys", "user", images)
    return Synthesis(answer=f"ans:{len(hits)}:figs{len(figures)}",
                     citations=[Citation(1, "B", "C", 1)])


def test_engine_query_text_only():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]
    index = FakeIndex(hits)
    sc = FakeSynthClient()
    engine = Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                    synth_client=sc, synth_fn=capturing_synth)
    result = engine.query("normal icp?")
    assert isinstance(result, QueryResult)
    assert result.answer == "ans:2:figs0"
    assert index.called_with == ("normal icp?", [0.0, 1.0], 5)
    assert result.figures == []
    assert sc.captured["images"] == []


def test_engine_query_collects_figures(tmp_path):
    png = tmp_path / "p0012.png"
    png.write_bytes(b"PNGBYTES")
    hits = [
        Hit(id="a", book="Rhoton", chapter="Sellar", page=12, text="cs anatomy",
            has_figure=True, caption="Figure 12-1: cs", figure_path=str(png)),
        Hit(id="b", book="Greenberg", chapter="Tumors", page=40, text="text only"),
    ]
    sc = FakeSynthClient()
    engine = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                    synth_client=sc, synth_fn=capturing_synth)
    result = engine.query("cavernous sinus?")
    assert len(result.figures) == 1
    fig = result.figures[0]
    assert isinstance(fig, Figure)
    assert fig.source_n == 1
    assert fig.book == "Rhoton"
    assert fig.page == 12
    assert fig.image_path == str(png)
    assert sc.captured["images"] == [b"PNGBYTES"]  # bytes read from disk


def test_engine_query_respects_max_figure_images(tmp_path):
    png = tmp_path / "p1.png"
    png.write_bytes(b"X")
    hits = [Hit(id=str(i), book="Rhoton", chapter="C", page=i, text="t",
                has_figure=True, caption="cap", figure_path=str(png))
            for i in range(1, 4)]

    class Cfg(FakeConfig):
        rerank_k = 5
        max_figure_images = 2

    sc = FakeSynthClient()
    engine = Engine(Cfg(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                    synth_client=sc, synth_fn=capturing_synth)
    result = engine.query("q")
    # same figure_path dedupes to one figure regardless of the cap
    assert len(result.figures) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_query.py -v`
Expected: FAIL — `Engine` takes `client=`, not `synth_client=`; no `Figure`.

- [ ] **Step 3: Rewrite `engine/query.py`**

```python
from dataclasses import dataclass, field

from .config import load_config
from .embed import Embedder
from .index import Index
from .rerank import Reranker
from .synthesize import synthesize
from .synth_clients import make_synth_client


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
                 synth_fn=synthesize):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.synth_client = synth_client
        self.synth_fn = synth_fn

    def _collect_figures(self, hits):
        out = []
        seen = set()
        for i, h in enumerate(hits, 1):
            if h.has_figure and h.figure_path and h.figure_path not in seen:
                seen.add(h.figure_path)
                out.append(Figure(source_n=i, book=h.book,
                                  chapter=h.chapter or "", page=h.page,
                                  image_path=h.figure_path, caption=h.caption or ""))
            if len(out) >= self.config.max_figure_images:
                break
        return out

    @staticmethod
    def _read_image(path):
        with open(path, "rb") as f:
            return f.read()

    def query(self, question):
        qv = self.embedder.embed_query(question)
        hits = self.index.hybrid_search(question, qv, self.config.retrieve_k)
        top = self.reranker.rerank(question, hits, self.config.rerank_k)
        figures = self._collect_figures(top)
        images = [self._read_image(f.image_path) for f in figures]
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
    _engine = Engine(config, embedder, index, reranker, synth_client)
    return _engine


def query(question, config=None):
    return get_engine(config).query(question)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_query.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/query.py tests/test_query.py
git commit -m "feat: collect figures + images through the query() seam"
```

---

### Task 9: Update eval harness and CLI for the new signature

**Files:**
- Modify: `eval/run_eval.py`
- Modify: `cli/ask.py`

The Phase 1 retrieval gate's `--synthesize` path calls `engine.synth_fn(q, top, engine.client, engine.config.openrouter_model)` — this must move to the new signature.

- [ ] **Step 1: Fix `eval/run_eval.py`**

In `eval/run_eval.py`, replace the `--synthesize` block:

```python
        if args.synthesize:
            # Reuse the passages already retrieved/reranked above.
            syn = engine.synth_fn(q, top, [], [], engine.synth_client)
            print(f"    answer: {syn.answer[:600]}\n")
```

- [ ] **Step 2: Verify retrieval gate still imports/runs (no LLM call)**

Run: `python3 -m eval.run_eval --help`
Expected: argparse help prints, no import error.

- [ ] **Step 3: Update `cli/ask.py` to print figures**

In `cli/ask.py`, after the existing sources loop, add:

```python
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")
```

- [ ] **Step 4: Commit**

```bash
git add eval/run_eval.py cli/ask.py
git commit -m "feat: update eval + CLI for multimodal synth signature and figures"
```

---

### Task 10: Update the build-index script to render figures

**Files:**
- Modify: `scripts/build_index.py`

- [ ] **Step 1: Pass render flags + report figure counts**

In `scripts/build_index.py`, replace the read loop's `extract_pages(pdf)` call with:

```python
        recs = extract_pages(pdf, render=True, assets_dir=cfg.assets_dir,
                             dpi=cfg.figure_dpi,
                             area_threshold=cfg.figure_area_threshold)
```

In the coverage-report print loop, extend the printed line to include figures:

```python
    for book, stats in coverage_from_records(records).items():
        print(f"  {book}: {stats['pages_with_text']}/{stats['pages']} pages "
              f"with text ({stats['coverage'] * 100:.1f}%), "
              f"{stats['pages_with_figures']} figure pages")
```

- [ ] **Step 2: Smoke-test the script wiring (no full build)**

Run: `python3 -c "import scripts.build_index"`
Expected: imports cleanly (no syntax/wiring error).

- [ ] **Step 3: Commit**

```bash
git add scripts/build_index.py
git commit -m "feat: render figure pages during index build; report figure counts"
```

---

### Task 11: Minimal Streamlit viewer

**Files:**
- Create: `app/__init__.py`
- Create: `app/streamlit_app.py`

No unit test (UI surface); verified by launching it in Task 13.

- [ ] **Step 1: Create the package marker**

Create `app/__init__.py` (empty file).

- [ ] **Step 2: Create `app/streamlit_app.py`**

```python
import streamlit as st

from engine.query import query

st.set_page_config(page_title="Neuro Textbook RAG", layout="wide")
st.title("Neurosurgery Textbook RAG")
st.caption("Citation-grounded answers from your textbook corpus. Decision-support only.")

q = st.text_input("Ask a clinical or anatomy question")

if q:
    with st.spinner("Searching textbooks..."):
        result = query(q)

    st.markdown(result.answer)

    if result.figures:
        st.subheader("Figures")
        cols = st.columns(min(3, len(result.figures)))
        for col, f in zip(cols, result.figures):
            with col:
                st.image(
                    f.image_path,
                    caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                    use_container_width=True,
                )

    st.subheader("Sources")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        st.write(f"[{c.n}] {loc}")
```

- [ ] **Step 3: Commit**

```bash
git add app/__init__.py app/streamlit_app.py
git commit -m "feat: minimal Streamlit viewer for answers + figures"
```

---

### Task 12: Figure-retrieval evaluation gate

**Files:**
- Create: `eval/figure_answers.yaml`
- Create: `eval/figure_eval.py`

- [ ] **Step 1: Create the figure answer set**

Create `eval/figure_answers.yaml`:

```yaml
# Visual / figure retrieval gate. Each case: a question + a substring expected in a
# retrieved book name, optionally an expected page. PASS if a FIGURE-bearing hit
# from the expected book (and page, if given) is in the reranked top hits.
# Tune these to your actual corpus and known plates after the first run.
- question: "Show the microsurgical anatomy of the cavernous sinus."
  expect_book_contains: "Rhoton"
- question: "Lateral view of the circle of Willis arterial anatomy."
  expect_book_contains: "Rhoton"
- question: "Anatomy of the petroclival region and Meckel's cave."
  expect_book_contains: "Fukushima"
- question: "Axial CT appearance of an acute epidural hematoma."
  expect_book_contains: "neuroradiology"
- question: "Angiographic appearance of a giant ICA aneurysm."
  expect_book_contains: "neurovascular"
```

- [ ] **Step 2: Create `eval/figure_eval.py`**

```python
import argparse

import yaml

from engine.query import get_engine


def main():
    ap = argparse.ArgumentParser(
        description="Figure-retrieval gate: did a figure page from the expected "
                    "book/page get surfaced?")
    ap.add_argument("--set", default="eval/figure_answers.yaml")
    ap.add_argument("--synthesize", action="store_true",
                    help="Also run full multimodal query() and print the answer "
                         "+ which figures were shown, for blinded faithfulness review")
    args = ap.parse_args()

    with open(args.set) as f:
        cases = yaml.safe_load(f)
    engine = get_engine()
    passed = 0
    for case in cases:
        q = case["question"]
        qv = engine.embedder.embed_query(q)
        hits = engine.index.hybrid_search(q, qv, engine.config.retrieve_k)
        top = engine.reranker.rerank(q, hits, engine.config.rerank_k)
        want_book = case["expect_book_contains"].lower()
        want_page = case.get("expect_page")
        fig_hits = [h for h in top if h.has_figure
                    and want_book in h.book.lower()
                    and (want_page is None or h.page == want_page)]
        ok = len(fig_hits) > 0
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"    figure hits in top: "
              f"{[(h.book, h.page) for h in top if h.has_figure]}")
        if args.synthesize:
            result = engine.query(q)
            print(f"    answer: {result.answer[:600]}")
            print(f"    figures shown: "
                  f"{[(fg.book, fg.page) for fg in result.figures]}\n")
    print(f"\nFigure-retrieval gate: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-test wiring (no index needed)**

Run: `python3 -c "import yaml; yaml.safe_load(open('eval/figure_answers.yaml'))"`
Expected: parses without error (valid YAML).

- [ ] **Step 4: Commit**

```bash
git add eval/figure_answers.yaml eval/figure_eval.py
git commit -m "feat: figure-retrieval evaluation gate + blinded synthesis review"
```

---

### Task 13: Full verification — suite, rebuild, gates, viewer, README

**Files:**
- Modify: `README.md`

This task has no new tests; it runs everything end-to-end and documents Phase 2. The index rebuild and live Vertex calls require the real corpus + GCP auth, so the steps below are the human-run validation that gates the feature.

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest -v`
Expected: all Phase 1 + Phase 2 unit tests PASS; integration tests PASS (LanceDB round-trips).

- [ ] **Step 2: Authenticate to GCP for Vertex**

Tell the user to run (interactive, in their own shell):
`gcloud auth application-default login`
and set `GOOGLE_CLOUD_PROJECT` in `.env`. Confirm `SYNTH_PROVIDER=vertex` and `VERTEX_MODEL` are set (default `gemini-2.5-flash`; switch to `gemini-3-flash-preview` only if available on Vertex in their project).

- [ ] **Step 3: Rebuild the index with figure detection/rendering**

Run: `python3 -m scripts.build_index`
Expected: coverage report now prints `N figure pages` per book; PNGs appear under `assets/figures/<book>/`. Spot-check that atlas books (Rhoton/Fukushima) report many figure pages and a text-only book reports few.

- [ ] **Step 4: Run the figure-retrieval gate (retrieval only)**

Run: `python3 -m eval.figure_eval`
Expected: prints PASS/FAIL per case and a `Figure-retrieval gate: X/Y passed`. If recall is poor, tune `eval/figure_answers.yaml` to real plates and/or lower `FIGURE_AREA_THRESHOLD`. **Decision point:** if recall stays weak after tuning, that is the documented trigger to add Approach B (BiomedCLIP) — do NOT silently ship weak retrieval.

- [ ] **Step 5: Run the blinded figure-synthesis gate**

Run: `python3 -m eval.figure_eval --synthesize`
Expected: for each case, a cited answer + the figures shown. Hand these to an independent reviewer (the Phase 1 neurosurgeon-agent pattern) for blinded faithfulness: does the answer match what the cited figure actually shows? This is the go/no-go before trusting the feature.

- [ ] **Step 6: Launch the viewer and confirm a figure renders**

Run: `streamlit run app/streamlit_app.py --server.address 0.0.0.0`
Expected: open the local URL, ask an anatomy question (e.g., cavernous sinus), and confirm the answer + at least one figure image + citations render. Confirm it's reachable from the phone on the same LAN.

- [ ] **Step 7: Update README**

Add a "Phase 2 — figure retrieval" section to `README.md` covering: the new `.env` keys, `gcloud auth application-default login`, that a re-index is required, how to run `eval/figure_eval.py`, and how to launch the Streamlit viewer. Note the known limitations (whole-page display; text-driven retrieval; Approach B is the fallback if recall is weak).

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: Phase 2 figure retrieval — setup, gates, viewer, limitations"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** figure detection (T2/T3), page rendering (T2/T3), schema columns (T4/T5), multimodal synthesis (T6), Vertex/OpenRouter unify + fallback (T7), `figures[]` on the seam (T8), cost caps `MAX_FIGURE_IMAGES`/`FIGURE_DPI` (T1/T8), Streamlit viewer (T11), blinded retrieval + synthesis gates (T12/T13), re-index requirement (T13). All spec sections map to a task.
- **Type consistency:** new fields `has_figure: bool`, `caption: Optional[str]`, `figure_path: Optional[str]` are added with defaults to `PageRecord`, `Chunk`, and `Hit`; `Figure` (source_n, book, chapter, page, image_path, caption) is defined once in `query.py` and consumed by `synthesize._figure_note` (uses `.source_n/.book/.page`) and the viewer/CLI (use `.image_path/.caption`). `synth_client.generate(system, user, images)` signature is identical across the fake, both adapters, and call sites.
- **Caption is not double-indexed:** captions already live in page text (extracted from it), so they are already embedded/FTS-searchable; `caption` is stored only as display/citation metadata. (This refines the spec's "fold caption into indexed text" — folding would duplicate.)
