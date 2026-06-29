# Streaming Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream the Ask answer (tokens + sources + figures incrementally) and persist in-progress/completed responses so refresh/navigation never loses progress.

**Architecture:** An Ask request becomes a server-owned **job** (in-memory, daemon thread runs the pipeline) exposed as a replayable **SSE event log**. The default *woven* synthesis streams token-by-token via a new `generate_stream` on the synth clients; the browser is a thin reducer over the event log with a `localStorage` mirror that restores from a cursor. Streaming is additive — the existing blocking `POST /api/ask` is untouched.

**Tech Stack:** Python / FastAPI `StreamingResponse` (native SSE, no new dep) · `threading` · React + Vite · browser `EventSource` · `localStorage`.

## Global Constraints

- Install is `pip install -e .[dev]` only; `caseprep` is vendored — never touch external copies.
- **No new Python or JS dependencies.** SSE = FastAPI `StreamingResponse` + `media_type="text/event-stream"`; client = native `EventSource`.
- CI gate is **pytest** (`testpaths = ["tests", "vendor/caseprep/tests"]`). ruff/eslint/mypy are NOT gates.
- Web a11y: colored text on light surfaces uses `-ink` tokens, never `text-primary/success/amber`.
- The default Ask path is **woven** (`LITERATURE_WEAVE=true`): one integrated `[n]`+`[L#]` answer via `synthesize_woven`. That is the path we stream.
- Keep `POST /api/ask` (blocking, one-shot JSON) **unchanged** — `scripts/batch_ask.py` + `tests/test_api_ask_verification.py` depend on it.
- Cost note: the streamed synthesis is the SAME single LLM call as today (one `generate_stream` instead of one `generate`) — no extra paid calls. The empty-answer retry (rare) is a second call, exactly as today.

---

## File Structure

- `neuro_core/synth_clients.py` — **modify**: add `generate_stream()` to each client + a default fallback.
- `neuro_core/synthesize.py` — **modify**: factor out `build_citations()` and `build_synth_prompt()`; reuse in `synthesize()`.
- `neuro_caseboard/woven_synth.py` — **modify**: factor out `build_woven_prompt()`; reuse in `synthesize_woven()`.
- `neuro_caseboard/qa_stream.py` — **create**: `stream_answer(question, emit, ...)` orchestrator (domain-pure; emits event dicts of domain objects).
- `api/server.py` — **modify**: `AskJob` + `_ASK_JOBS` LRU + `_serialize_ask_event()` + `run_ask_job()` + `POST /api/ask/start` + `GET /api/ask/stream/{job_id}`.
- `web/src/lib/askStore.ts` — **create**: `AskState`, `applyAskEvent()` reducer, `loadAsk/saveAsk/clearAsk` over `localStorage`.
- `web/src/lib/api.ts` — **modify**: `startAsk()` + `openAskStream()` + streamed-event types.
- `web/src/pages/Ask.tsx` — **modify**: drive the stream, reduce + persist events, restore on mount, render incrementally.
- Tests: `tests/neuro_core/test_synth_stream.py`, `tests/neuro_core/test_synth_builders.py`, `tests/test_qa_stream.py`, `tests/test_api_ask_stream.py`, `web/src/lib/askStore.test.ts`.

---

## Task 1: `generate_stream` on the synth clients

**Files:**
- Modify: `neuro_core/synth_clients.py`
- Test: `tests/neuro_core/test_synth_stream.py`

**Interfaces:**
- Produces: `OpenRouterSynthClient.generate_stream(system, user, images) -> Iterator[str]` (also inherited/overridden by `LocalSynthClient`); `VertexSynthClient.generate_stream(...) -> Iterator[str]`. Each yields text deltas whose concatenation equals what `generate()` would return.

- [ ] **Step 1: Write the failing test**

```python
# tests/neuro_core/test_synth_stream.py
"""generate_stream yields deltas that concatenate to the full answer."""
from neuro_core.synth_clients import OpenRouterSynthClient, LocalSynthClient, VertexSynthClient


class _FakeDelta:
    def __init__(self, content): self.content = content
class _FakeChoice:
    def __init__(self, content): self.delta = _FakeDelta(content)
class _FakeChunk:
    def __init__(self, content): self.choices = [_FakeChoice(content)]


class _FakeOpenAI:
    """Stands in for the openai client; records the create() kwargs and returns a chunk stream."""
    def __init__(self, parts): self._parts = parts; self.kwargs = None
    @property
    def chat(self): return self
    @property
    def completions(self): return self
    def create(self, **kwargs):
        self.kwargs = kwargs
        return iter([_FakeChunk(p) for p in self._parts] + [_FakeChunk(None)])


def test_openrouter_generate_stream_concats():
    fake = _FakeOpenAI(["Hel", "lo ", "world"])
    c = OpenRouterSynthClient(api_key="x", model="m", client=fake)
    out = list(c.generate_stream("sys", "user", []))
    assert "".join(out) == "Hello world"
    assert fake.kwargs["stream"] is True          # actually streamed, not a single shot
    assert fake.kwargs["model"] == "m"


def test_local_generate_stream_is_text_only():
    fake = _FakeOpenAI(["a", "b"])
    c = LocalSynthClient(base_url="http://local", model="m", client=fake)
    out = list(c.generate_stream("sys", "user", [b"IMAGEBYTES"]))
    assert "".join(out) == "ab"
    # text-only: the user message is a plain string, no image parts leak to a local model
    assert fake.kwargs["messages"][1]["content"] == "user"


def test_vertex_generate_stream_concats():
    class _Chunk:
        def __init__(self, t): self.text = t
    class _Models:
        def generate_content_stream(self, **kwargs):
            return iter([_Chunk("foo"), _Chunk(""), _Chunk("bar"), _Chunk(None)])
    class _FakeGenai:
        models = _Models()
    c = VertexSynthClient(project="p", location="l", model="m", client=_FakeGenai())
    out = list(c.generate_stream("sys", "user", []))
    assert "".join(out) == "foobar"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/neuro_core/test_synth_stream.py -q`
Expected: FAIL — `AttributeError: 'OpenRouterSynthClient' object has no attribute 'generate_stream'`.

- [ ] **Step 3: Implement `generate_stream` on each client**

In `neuro_core/synth_clients.py`, add to `OpenRouterSynthClient` (after `generate`):

```python
    def generate_stream(self, system, user, images):
        """Yield answer text deltas (concatenation == generate()'s return). Same prompt/
        image handling as generate(), with stream=True."""
        content = [{"type": "text", "text": user}]
        for img in images:
            b64 = base64.b64encode(img).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        stream = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
```

Add to `LocalSynthClient` (text-only, mirrors its `generate`):

```python
    def generate_stream(self, system, user, images):
        stream = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
```

Add to `VertexSynthClient`:

```python
    def generate_stream(self, system, user, images):
        from google.genai import types
        parts = [types.Part.from_text(text=user)]
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        stream = self.client.models.generate_content_stream(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0.1),
        )
        for chunk in stream:
            if getattr(chunk, "text", None):
                yield chunk.text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/neuro_core/test_synth_stream.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/synth_clients.py tests/neuro_core/test_synth_stream.py
git commit -m "feat(synth): generate_stream on OpenRouter/Local/Vertex clients"
```

---

## Task 2: Factor shared citation + prompt builders

**Files:**
- Modify: `neuro_core/synthesize.py`, `neuro_caseboard/woven_synth.py`
- Test: `tests/neuro_core/test_synth_builders.py`

**Interfaces:**
- Produces: `neuro_core.synthesize.build_citations(hits, figures) -> list[Citation]`; `neuro_core.synthesize.build_synth_prompt(question, hits, figures, variant_directive=None) -> str`; `neuro_caseboard.woven_synth.build_woven_prompt(question, hits, figures, records, variant_directive=None) -> str`.
- Consumes: `Hit(book, chapter, page, text, has_figure, figure_path)`, `Figure(source_n, book, chapter, page, caption)`, existing private formatters `_format_passages/_appended_figures/_format_appended/_figure_note` and `literature.synth._format_studies`.

- [ ] **Step 1: Write the failing test**

```python
# tests/neuro_core/test_synth_builders.py
"""The factored builders match the inline construction the synth functions used."""
from dataclasses import dataclass


@dataclass
class _Hit:
    book: str; chapter: str; page: int; text: str
    has_figure: bool = False; figure_path: str = None


@dataclass
class _Fig:
    source_n: int; book: str; chapter: str; page: int; caption: str = ""


def test_build_citations_numbers_hits_then_appends_figures():
    from neuro_core.synthesize import build_citations
    hits = [_Hit("BookA", "Ch1", 10, "passage one"),
            _Hit("BookB", "", 20, "passage two")]
    # an appended figure has source_n > len(hits)
    figs = [_Fig(source_n=3, book="BookC", chapter="Ch9", page=30, caption="a plate")]
    cites = build_citations(hits, figs)
    assert [(c.n, c.book, c.page) for c in cites] == [
        (1, "BookA", 10), (2, "BookB", 20), (3, "BookC", 30)]
    assert cites[0].text == "passage one"      # hit citations carry the chunk text
    assert cites[2].text == ""                 # appended-figure citation has no chunk text


def test_build_synth_prompt_contains_question_and_passages():
    from neuro_core.synthesize import build_synth_prompt
    hits = [_Hit("BookA", "Ch1", 10, "passage one")]
    p = build_synth_prompt("what supplies X?", hits, [], variant_directive="Answer for 'left' ONLY.")
    assert "Question: what supplies X?" in p
    assert "[1] BookA, Ch1, p.10:" in p
    assert "Answer for 'left' ONLY." in p


def test_build_woven_prompt_includes_studies_block():
    from neuro_caseboard.woven_synth import build_woven_prompt
    hits = [_Hit("BookA", "Ch1", 10, "passage one")]

    @dataclass
    class _Rec:
        n: int = 1; title: str = "A study"; journal: str = "J"; year: int = 2021
        authors: str = "Doe"; abstract: str = "abstract text"; pmid: str = "1"
    p = build_woven_prompt("q", hits, [], [_Rec()])
    assert "Textbook passages:" in p
    assert "Contemporary studies:" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/neuro_core/test_synth_builders.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_citations'`.

- [ ] **Step 3: Add the builders and refactor the synth functions**

In `neuro_core/synthesize.py`, add (after `_format_appended`):

```python
def build_citations(hits, figures):
    """Citations for an answer: one per passage hit (numbered 1..n, carrying chunk text),
    then appended figure sources (source_n > n, no chunk text). Shared by synthesize() and
    the woven path so the [n] namespace is constructed identically everywhere."""
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page, text=h.text)
        for i, h in enumerate(hits, 1)
    ]
    for f in _appended_figures(hits, figures):
        citations.append(Citation(n=f.source_n, book=f.book,
                                  chapter=f.chapter or "", page=f.page))
    return citations


def build_synth_prompt(question, hits, figures, variant_directive=None):
    """The non-woven user prompt: question + passages + appended figures + figure note."""
    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if variant_directive:
        user += "\n\n" + variant_directive
    return user
```

Refactor `synthesize()` to reuse them (replaces the inline prompt + citation construction):

```python
def synthesize(question, hits, figures, images, synth_client, variant_directive=None):
    user = build_synth_prompt(question, hits, figures, variant_directive)
    answer = synth_client.generate(SYSTEM_PROMPT, user, images)
    return Synthesis(answer=answer, citations=build_citations(hits, figures))
```

In `neuro_caseboard/woven_synth.py`, add `build_woven_prompt` and refactor `synthesize_woven`:

```python
def build_woven_prompt(question, hits, figures, records, variant_directive=None):
    from neuro_core.synthesize import _format_passages, _appended_figures, _format_appended, _figure_note
    from neuro_caseboard.literature.synth import _format_studies
    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nTextbook passages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if records:
        user += f"\n\nContemporary studies:\n{_format_studies(records)}"
    if variant_directive:
        user += "\n\n" + variant_directive
    return user


def synthesize_woven(question, hits, figures, images, records, synth_client,
                     *, variant_directive=None) -> WovenSynthesis:
    from neuro_core.synthesize import build_citations
    user = build_woven_prompt(question, hits, figures, records, variant_directive)
    answer = synth_client.generate(WOVEN_SYSTEM, user, images)
    return WovenSynthesis(answer=answer, citations=build_citations(hits, figures),
                          records=list(records))
```

- [ ] **Step 4: Run the new test AND the existing synth tests for no-regression**

Run: `python -m pytest tests/neuro_core/test_synth_builders.py tests/neuro_core -k "synth or woven" -q`
Expected: PASS (new builders pass; existing `synthesize`/`synthesize_woven` tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/synthesize.py neuro_caseboard/woven_synth.py tests/neuro_core/test_synth_builders.py
git commit -m "refactor(synth): extract build_citations + prompt builders for reuse"
```

---

## Task 3: `stream_answer` orchestrator

**Files:**
- Create: `neuro_caseboard/qa_stream.py`
- Test: `tests/test_qa_stream.py`

**Interfaces:**
- Produces: `stream_answer(question, emit, *, config=None, force=False, skip_disambiguation=False, lit_config=None, synth_client=None, plan_a=None, retrieve_b=None) -> None`. `emit` is `Callable[[dict], None]`; events are domain dicts with a `type` key (values may be domain objects — the server serializes). Event order on the happy path: `sources`, `figures`, `answer_delta`*, `answer`, `literature`, `verification`, `done`.
- Consumes: `plan_retrieval` (Task seam, returns `RetrievalBundle | Clarification`), `_retrieve_literature_for_weave`, `build_citations`, `build_woven_prompt`, `WOVEN_SYSTEM`, `is_refusal`, `REFUSAL`, `verify_answer`, `LiteratureSection`/`LiteratureCitation`, and `synth_client.generate_stream` (Task 1).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_stream.py
"""stream_answer emits sources/figures before tokens, an authoritative answer, then done."""
from dataclasses import dataclass, field
from neuro_caseboard.qa_stream import stream_answer


@dataclass
class _Hit:
    book: str = "BookA"; chapter: str = "Ch1"; page: int = 10; text: str = "passage"
    has_figure: bool = False; figure_path: str = None


@dataclass
class _Bundle:
    question: str; hits: list; figures: list = field(default_factory=list)
    images: list = field(default_factory=list); variant: object = None


class _FakeStreamClient:
    def __init__(self, parts): self._parts = parts
    def generate(self, system, user, images): return "".join(self._parts)
    def generate_stream(self, system, user, images):
        for p in self._parts: yield p


def _collect(**kw):
    events = []
    stream_answer("q", events.append, **kw)
    return events


def test_order_sources_before_tokens_then_authoritative_answer():
    bundle = _Bundle("q", [_Hit()], figures=[])
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["Hel", "lo [1]"]),
    )
    types = [e["type"] for e in events]
    assert types.index("sources") < types.index("answer_delta")
    assert types.index("figures") < types.index("answer_delta")
    assert types[-1] == "done"
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["answer"] == "Hello [1]"          # == concatenated deltas
    assert answer_ev["refusal"] is False
    assert [e["text"] for e in events if e["type"] == "answer_delta"] == ["Hel", "lo [1]"]


def test_refusal_drops_sources_and_figures():
    @dataclass
    class _Fig:
        source_n: int = 1; book: str = "B"; chapter: str = ""; page: int = 1; caption: str = ""
    bundle = _Bundle("q", [_Hit()], figures=[_Fig()])
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["Not found in the provided sources."]),
    )
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["refusal"] is True
    assert answer_ev["citations"] == [] and answer_ev["figures"] == []


def test_clarification_short_circuits():
    from neuro_core.query import Clarification
    events = _collect(
        plan_a=lambda: Clarification(question="q", variants=[]),
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["x"]),
    )
    assert [e["type"] for e in events] == ["clarification", "done"]


def test_variant_prefix_is_first_delta():
    from neuro_core.query import VariantRewrite
    bundle = _Bundle("q", [_Hit()], variant=VariantRewrite(label="left ICA", rewrite="q left"))
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["body [1]"]),
    )
    deltas = [e["text"] for e in events if e["type"] == "answer_delta"]
    assert deltas[0].startswith("**Assuming left ICA")
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["answer"] == "".join(deltas)      # persisted final == streamed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_qa_stream.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.qa_stream'`.

- [ ] **Step 3: Implement the orchestrator**

```python
# neuro_caseboard/qa_stream.py
"""Streaming Ask orchestrator: emit retrieval (sources/figures) first, then woven-synthesis
token deltas, then literature/verification. Mirrors qa._answer_question_woven's retrieval,
empty-guard, refusal, and variant handling — but streams the synthesis call.

`emit` receives domain event dicts (values may be domain objects); serialization to the wire
shape lives in the API layer (api.server._serialize_ask_event)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from neuro_caseboard.qa import (LiteratureSection, LiteratureCitation,
                                _retrieve_literature_for_weave)

_log = logging.getLogger(__name__)


def _emit_batch(emit, qr):
    """Emit a completed QAResult (from the blocking fallback) as one batch + done."""
    emit({"type": "sources", "citations": list(qr.citations or [])})
    emit({"type": "figures", "figures": list(qr.figures or [])})
    emit({"type": "answer", "answer": qr.answer, "citations": list(qr.citations or []),
          "figures": list(qr.figures or []), "refusal": False})
    emit({"type": "literature", "literature": getattr(qr, "literature", None)})
    emit({"type": "verification", "verification": getattr(qr, "verification", None)})
    emit({"type": "done"})


def _fallback(question, emit, *, config, force, skip_disambiguation):
    from neuro_caseboard.qa import answer_question
    from neuro_core.query import Clarification
    qr = answer_question(question, config=config, force=force,
                         skip_disambiguation=skip_disambiguation)
    if isinstance(qr, Clarification):
        emit({"type": "clarification", "question": getattr(qr, "question", question),
              "variants": list(getattr(qr, "variants", []))})
        emit({"type": "done"})
        return
    _emit_batch(emit, qr)


def stream_answer(question, emit, *, config=None, force=False, skip_disambiguation=False,
                  lit_config=None, synth_client=None, plan_a=None, retrieve_b=None):
    from neuro_core.query import Clarification, _variant_directive
    from neuro_core.synthesize import REFUSAL, is_refusal, build_citations
    from neuro_caseboard.woven_synth import WOVEN_SYSTEM, build_woven_prompt

    if lit_config is None and plan_a is None and retrieve_b is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
        if not lit_config.weave:                       # separate-lane config → blocking fallback
            _fallback(question, emit, config=config, force=force,
                      skip_disambiguation=skip_disambiguation)
            return

    try:
        if synth_client is None:
            from neuro_core.config import load_config
            from neuro_core.synth_clients import make_synth_client
            synth_client = make_synth_client(config or load_config())
        if plan_a is None:
            from neuro_core.query import plan_retrieval
            def plan_a():
                return plan_retrieval(question, config=config, force=force,
                                      skip_disambiguation=skip_disambiguation)
        if retrieve_b is None:
            def retrieve_b():
                return _retrieve_literature_for_weave(question, lit_config=lit_config,
                                                      synth_client=synth_client)

        with ThreadPoolExecutor(max_workers=2) as ex:
            fa = ex.submit(plan_a)
            fb = ex.submit(retrieve_b)
            plan = fa.result()                          # Lane A errors propagate
            if isinstance(plan, Clarification):
                emit({"type": "clarification",
                      "question": getattr(plan, "question", question),
                      "variants": list(getattr(plan, "variants", []))})
                emit({"type": "done"})
                return
            try:
                records = fb.result()
            except Exception:
                _log.debug("woven literature lane raised", exc_info=True)
                records = []

        citations = build_citations(plan.hits, plan.figures)
        emit({"type": "sources", "citations": citations})
        emit({"type": "figures", "figures": list(plan.figures or [])})

        directive = _variant_directive(plan.variant.label) if plan.variant else None
        prefix = ""
        if plan.variant is not None:
            prefix = (f"**Assuming {plan.variant.label} (most consistent with retrieved "
                      "sources).**\n\n")
            emit({"type": "answer_delta", "text": prefix})

        def _stream_body():
            user = build_woven_prompt(plan.question, plan.hits, plan.figures, records, directive)
            parts = []
            for delta in synth_client.generate_stream(WOVEN_SYSTEM, user, plan.images):
                if not delta:
                    continue
                parts.append(delta)
                emit({"type": "answer_delta", "text": delta})
            return "".join(parts)

        body = _stream_body()
        # Empty-answer guard (parity with _answer_question_woven): retry once, then REFUSAL.
        if not body.strip():
            body = _stream_body()
            if not body.strip():
                emit({"type": "answer", "answer": REFUSAL, "citations": [], "figures": [],
                      "refusal": True})
                emit({"type": "literature", "literature": None})
                emit({"type": "verification", "verification": None})
                emit({"type": "done"})
                return

        full_answer = prefix + body
        refusal = is_refusal(body)
        if refusal:
            # Abstention: retrieval-derived sources/figures/literature are spurious.
            emit({"type": "answer", "answer": body, "citations": [], "figures": [],
                  "refusal": True})
            emit({"type": "literature", "literature": None})
            emit({"type": "verification", "verification": None})
            emit({"type": "done"})
            return

        emit({"type": "answer", "answer": full_answer, "citations": citations,
              "figures": list(plan.figures or []), "refusal": False})

        lit = None
        if records:
            cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                        year=r.year, doi=r.doi, url=r.url,
                                        abstract=getattr(r, "abstract", "") or "")
                     for i, r in enumerate(records, 1)]
            lit = LiteratureSection(narrative="", citations=cites)
        emit({"type": "literature", "literature": lit})

        from neuro_caseboard.answer_verify import verify_answer
        premises = {str(getattr(c, "n", i)): getattr(c, "text", "") or ""
                    for i, c in enumerate(citations, 1)}
        for i, r in enumerate(records or [], 1):
            premises[f"L{i}"] = getattr(r, "abstract", "") or ""
        emit({"type": "verification", "verification": verify_answer(full_answer, premises)})
        emit({"type": "done"})
    except Exception:
        # Any streaming-path failure degrades to the proven blocking path (still persisted).
        _log.debug("stream_answer failed; falling back to blocking answer_question", exc_info=True)
        _fallback(question, emit, config=config, force=force,
                  skip_disambiguation=skip_disambiguation)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_qa_stream.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/qa_stream.py tests/test_qa_stream.py
git commit -m "feat(qa): stream_answer woven orchestrator (sources/figures, then token deltas)"
```

---

## Task 4: Server job store + streaming endpoints

**Files:**
- Modify: `api/server.py`
- Test: `tests/test_api_ask_stream.py`

**Interfaces:**
- Produces: `POST /api/ask/start {question, skip_disambiguation?}` → `{"job_id": str}`; `GET /api/ask/stream/{job_id}?cursor=N` → SSE (`text/event-stream`) of `id: {i}\ndata: {json}\n\n`, replaying `events[cursor:]` then tailing until a `done` event; 404 for unknown job.
- Consumes: `stream_answer` (Task 3), existing `_citation_dict/_figure_dict/_literature_dict/verification_to_dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_ask_stream.py
"""POST /api/ask/start returns a job id; the SSE stream replays the event log idempotently."""
import json
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _events_from_sse(text):
    out = []
    for line in text.splitlines():
        if line.startswith("data:"):
            out.append(json.loads(line[len("data:"):].strip()))
    return out


def _fake_stream_answer(question, emit, **kwargs):
    # neuro_core Citation / query.Figure are what the serializer expects.
    from neuro_core.synthesize import Citation
    emit({"type": "sources", "citations": [Citation(n=1, book="BookA", chapter="Ch1", page=10, text="t")]})
    emit({"type": "figures", "figures": []})
    emit({"type": "answer_delta", "text": "Hel"})
    emit({"type": "answer_delta", "text": "lo [1]"})
    emit({"type": "answer", "answer": "Hello [1]",
          "citations": [Citation(n=1, book="BookA", chapter="Ch1", page=10, text="t")],
          "figures": [], "refusal": False})
    emit({"type": "literature", "literature": None})
    emit({"type": "verification", "verification": None})
    emit({"type": "done"})


def test_start_then_stream_replays_full_log(monkeypatch):
    import api.server as server
    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)

    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    assert job_id

    body = client.get(f"/api/ask/stream/{job_id}?cursor=0").text
    events = _events_from_sse(body)
    assert [e["type"] for e in events][-1] == "done"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["answer"] == "Hello [1]"
    sources = next(e for e in events if e["type"] == "sources")
    assert sources["citations"][0]["book"] == "BookA"          # serialized via _citation_dict


def test_stream_from_cursor_is_idempotent(monkeypatch):
    import api.server as server
    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]

    full = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=0").text)
    # Reconnect from a later cursor → only the tail, no duplicates of earlier events.
    tail = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=3").text)
    assert tail == full[3:]


def test_unknown_job_404():
    import api.server as server
    client = TestClient(server.app)
    assert client.get("/api/ask/stream/nope?cursor=0").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_ask_stream.py -q`
Expected: FAIL — 404/405 on `/api/ask/start` (route not defined).

- [ ] **Step 3: Implement the job store, serializer, runner, and endpoints**

In `api/server.py`, add imports near the top (with the existing stdlib imports):

```python
import asyncio
import json
import threading
import uuid
from typing import Any
```

and `from fastapi.responses import StreamingResponse` (extend the existing fastapi.responses import).

Add the job machinery (near the `_DOSSIER_CACHE` block):

```python
# --- Ask streaming jobs ----------------------------------------------------------------------
# An Ask request is a server-owned job: a daemon thread runs the (synchronous) streaming
# orchestrator, appending serialized events to an append-only log. The SSE endpoint replays the
# log from a cursor and tails it live, so a refresh/reconnect resumes exactly where it left off.
# In-memory + single-process is intentional (single-user local tool); a server restart drops
# in-flight jobs and the client re-asks.  # ponytail: in-memory LRU, swap for a store if multi-user.

class AskJob:
    def __init__(self, job_id: str):
        self.id = job_id
        self.events: list[dict] = []
        self.done = False
        self._lock = threading.Lock()

    def emit(self, event: dict) -> None:
        with self._lock:
            self.events.append(_serialize_ask_event(event))
            if event.get("type") == "done":
                self.done = True

    def slice_from(self, cursor: int) -> tuple[list[dict], bool]:
        with self._lock:
            return self.events[cursor:], self.done


_ASK_JOBS: "OrderedDict[str, AskJob]" = OrderedDict()
_ASK_JOBS_MAX = 8


def _serialize_ask_event(ev: dict) -> dict:
    t = ev.get("type")
    if t == "sources":
        return {"type": "sources", "citations": [_citation_dict(c) for c in ev["citations"]]}
    if t == "figures":
        return {"type": "figures", "figures": [_figure_dict(f) for f in ev["figures"]]}
    if t == "answer_delta":
        return {"type": "answer_delta", "text": ev["text"]}
    if t == "answer":
        return {"type": "answer", "answer": ev["answer"], "refusal": bool(ev.get("refusal")),
                "citations": [_citation_dict(c) for c in ev.get("citations") or []],
                "figures": [_figure_dict(f) for f in ev.get("figures") or []]}
    if t == "literature":
        return {"type": "literature", "literature": _literature_dict(ev.get("literature"))}
    if t == "verification":
        return {"type": "verification",
                "verification": verification_to_dict(ev.get("verification"))}
    if t == "clarification":
        return {"type": "clarification", "question": ev.get("question", ""),
                "variants": [{"label": getattr(v, "label", ""), "rewrite": getattr(v, "rewrite", "")}
                             for v in ev.get("variants") or []]}
    # unavailable / error / done pass through unchanged
    return ev


def run_ask_job(job: AskJob, question: str, skip_disambiguation: bool) -> None:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_caseboard import qa_stream
    try:
        qa_stream.stream_answer(question, job.emit, force=True,
                                skip_disambiguation=skip_disambiguation)
    except GpuNotReadyError as e:
        job.emit({"type": "unavailable", "reason": f"GPU not ready: {e}"})
        job.emit({"type": "done"})
    except Exception as e:
        job.emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
        job.emit({"type": "done"})
    finally:
        if not job.done:                       # the orchestrator always ends with done, but be safe
            job.emit({"type": "done"})


@app.post("/api/ask/start")
def ask_start(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"error": "empty question"})
    job_id = uuid.uuid4().hex[:16]
    job = AskJob(job_id)
    _ASK_JOBS[job_id] = job
    _ASK_JOBS.move_to_end(job_id)
    while len(_ASK_JOBS) > _ASK_JOBS_MAX:
        _ASK_JOBS.popitem(last=False)
    threading.Thread(target=run_ask_job, args=(job, question, req.skip_disambiguation),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/ask/stream/{job_id}")
async def ask_stream(job_id: str, cursor: int = 0):
    job = _ASK_JOBS.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "unknown or expired job"})

    async def gen():
        i = cursor
        while True:
            pending, done = job.slice_from(i)
            for ev in pending:
                yield f"id: {i}\ndata: {json.dumps(ev)}\n\n"
                i += 1
            if done and i >= len(job.events):
                return
            await asyncio.sleep(0.05)          # ponytail: poll loop; threading.Condition if needed

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

> Note: `_serialize_ask_event` references `_citation_dict` etc., which are defined later in the file. Because it is only *called* at request time (never at import), define the job block anywhere after those helpers — place it just below `_literature_dict` to keep definition order clean.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_ask_stream.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the existing ask tests for no-regression**

Run: `python -m pytest tests/test_api_ask_verification.py tests/test_ask_error_handling.py -q`
Expected: PASS (the blocking `/api/ask` is unchanged).

- [ ] **Step 6: Commit**

```bash
git add api/server.py tests/test_api_ask_stream.py
git commit -m "feat(api): /api/ask/start + SSE /api/ask/stream job replay"
```

---

## Task 5: Web — persistence store + stream client

**Files:**
- Create: `web/src/lib/askStore.ts`
- Modify: `web/src/lib/api.ts`
- Test: `web/src/lib/askStore.test.ts`

**Interfaces:**
- Produces (`askStore.ts`): `AskState` type; `applyAskEvent(state, ev, index) -> AskState` (pure reducer; ignores `index < state.nextIndex` for dedup; appends `answer_delta`; replaces text/sources/figures on the authoritative `answer`); `loadAsk(storage)`, `saveAsk(storage, state)`, `clearAsk(storage)`.
- Produces (`api.ts`): `startAsk(question, skipDisambiguation?) -> Promise<{job_id: string}>`; `openAskStream(jobId, cursor, handlers) -> EventSource`; `AskEvent` discriminated union type.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/askStore.test.ts
import { describe, it, expect } from "vitest"
import { applyAskEvent, emptyAskState, loadAsk, saveAsk, type AskEvent } from "./askStore"

function feed(events: AskEvent[]) {
  let s = emptyAskState("q", "job1")
  events.forEach((e, i) => { s = applyAskEvent(s, e, i) })
  return s
}

describe("applyAskEvent", () => {
  it("appends answer deltas and tracks nextIndex", () => {
    const s = feed([
      { type: "sources", citations: [{ n: 1, book: "B", chapter: "C", page: 1, location: "B, C, p.1" }] },
      { type: "figures", figures: [] },
      { type: "answer_delta", text: "Hel" },
      { type: "answer_delta", text: "lo" },
    ])
    expect(s.answer).toBe("Hello")
    expect(s.sources.length).toBe(1)
    expect(s.nextIndex).toBe(4)
  })

  it("ignores events already seen (dedup on restore)", () => {
    let s = emptyAskState("q", "job1")
    s = applyAskEvent(s, { type: "answer_delta", text: "A" }, 0)
    s = applyAskEvent(s, { type: "answer_delta", text: "B" }, 1)
    // replay of index 0 and 1 must NOT double-append
    s = applyAskEvent(s, { type: "answer_delta", text: "A" }, 0)
    s = applyAskEvent(s, { type: "answer_delta", text: "B" }, 1)
    expect(s.answer).toBe("AB")
  })

  it("adopts the authoritative answer event (replace, not append)", () => {
    const s = feed([
      { type: "answer_delta", text: "draft" },
      { type: "answer", answer: "**Assuming X.**\n\nfinal [1]", refusal: false,
        citations: [{ n: 1, book: "B", chapter: "", page: 2, location: "B, p.2" }], figures: [] },
    ])
    expect(s.answer).toBe("**Assuming X.**\n\nfinal [1]")
    expect(s.sources[0].page).toBe(2)
    expect(s.status).toBe("answer")
  })

  it("clears sources/figures on a refusal answer", () => {
    const s = feed([
      { type: "sources", citations: [{ n: 1, book: "B", chapter: "", page: 1, location: "B, p.1" }] },
      { type: "answer", answer: "Not found in the provided sources.", refusal: true, citations: [], figures: [] },
    ])
    expect(s.sources).toEqual([])
  })

  it("marks done", () => {
    const s = feed([{ type: "done" }])
    expect(s.done).toBe(true)
  })
})

describe("store round-trip", () => {
  it("saves and loads", () => {
    const mem: Record<string, string> = {}
    const storage = { getItem: (k: string) => mem[k] ?? null, setItem: (k: string, v: string) => { mem[k] = v } }
    const s = feed([{ type: "answer_delta", text: "hi" }])
    saveAsk(storage, s)
    expect(loadAsk(storage)?.answer).toBe("hi")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/lib/askStore.test.ts`
Expected: FAIL — cannot resolve `./askStore`.

- [ ] **Step 3: Implement `askStore.ts`**

```ts
// web/src/lib/askStore.ts
// Persistent mirror of an in-flight / completed Ask response. The server owns the truth (a
// replayable event log); this is a local cache so a refresh/tab-change restores instantly and a
// reconnect resumes from `nextIndex`. Dedup is by event index — events already applied are ignored.
import type { Citation, Figure, Literature, Variant } from "./api"

interface Verification {
  n_cited_claims: number; n_unsupported: number; groundedness: number; unsupported_markers: string[]
}

export type AskEvent =
  | { type: "sources"; citations: Citation[] }
  | { type: "figures"; figures: Figure[] }
  | { type: "answer_delta"; text: string }
  | { type: "answer"; answer: string; refusal: boolean; citations: Citation[]; figures: Figure[] }
  | { type: "literature"; literature: Literature | null }
  | { type: "verification"; verification: Verification | null }
  | { type: "clarification"; question: string; variants: Variant[] }
  | { type: "unavailable"; reason: string }
  | { type: "error"; error: string }
  | { type: "done" }

export type AskStatus = "streaming" | "answer" | "clarification" | "unavailable" | "error"

export interface AskState {
  question: string
  jobId: string
  status: AskStatus
  answer: string
  sources: Citation[]
  figures: Figure[]
  literature: Literature | null
  verification: Verification | null
  variants: Variant[]
  reason: string        // unavailable/error message
  nextIndex: number     // next un-applied event index (the reconnect cursor)
  done: boolean
}

export function emptyAskState(question: string, jobId: string): AskState {
  return { question, jobId, status: "streaming", answer: "", sources: [], figures: [],
    literature: null, verification: null, variants: [], reason: "", nextIndex: 0, done: false }
}

export function applyAskEvent(state: AskState, ev: AskEvent, index: number): AskState {
  if (index < state.nextIndex) return state          // already applied — dedup on replay
  const s: AskState = { ...state, nextIndex: index + 1 }
  switch (ev.type) {
    case "sources": s.sources = ev.citations; break
    case "figures": s.figures = ev.figures; break
    case "answer_delta": s.answer = state.answer + ev.text; break
    case "answer":
      s.answer = ev.answer; s.status = "answer"
      s.sources = ev.refusal ? [] : ev.citations
      s.figures = ev.refusal ? [] : ev.figures
      break
    case "literature": s.literature = ev.literature; break
    case "verification": s.verification = ev.verification; break
    case "clarification": s.status = "clarification"; s.variants = ev.variants; break
    case "unavailable": s.status = "unavailable"; s.reason = ev.reason; break
    case "error": s.status = "error"; s.reason = ev.error; break
    case "done": s.done = true; break
  }
  return s
}

const KEY = "neuro.ask.v1"

export function loadAsk(storage: { getItem(k: string): string | null }): AskState | null {
  try { return JSON.parse(storage.getItem(KEY) ?? "null") as AskState | null } catch { return null }
}
export function saveAsk(storage: { setItem(k: string, v: string): void }, state: AskState): void {
  storage.setItem(KEY, JSON.stringify(state))
}
export function clearAsk(storage: { setItem(k: string, v: string): void }): void {
  storage.setItem(KEY, "null")
}
```

- [ ] **Step 4: Implement `startAsk` + `openAskStream` in `api.ts`**

Add to `web/src/lib/api.ts` (after `askQuestion`); re-export `AskEvent` is not needed — it lives in askStore. Import the event type there.

```ts
// ----- Ask streaming (job + SSE) -------------------------------------------------------------
import type { AskEvent } from "./askStore"

export async function startAsk(question: string, skipDisambiguation = false): Promise<{ job_id: string }> {
  const res = await fetch("/api/ask/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, skip_disambiguation: skipDisambiguation }),
  })
  return (await res.json()) as { job_id: string }
}

/** Open the SSE replay/tail for a job from `cursor`. The caller's onEvent receives (event, index);
 *  it MUST close the source on a terminal event (done/error/unavailable/clarification) — EventSource
 *  auto-reconnects on any close otherwise. onError fires on a transport drop. */
export function openAskStream(
  jobId: string,
  cursor: number,
  handlers: { onEvent: (ev: AskEvent, index: number) => void; onError?: () => void },
): EventSource {
  const es = new EventSource(`/api/ask/stream/${jobId}?cursor=${cursor}`)
  es.onmessage = (m) => {
    const index = m.lastEventId ? Number(m.lastEventId) : 0
    handlers.onEvent(JSON.parse(m.data) as AskEvent, index)
  }
  es.onerror = () => handlers.onError?.()
  return es
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run src/lib/askStore.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/askStore.ts web/src/lib/askStore.test.ts web/src/lib/api.ts
git commit -m "feat(web): askStore reducer + startAsk/openAskStream SSE client"
```

---

## Task 6: Web — wire Ask.tsx to the stream with restore

**Files:**
- Modify: `web/src/pages/Ask.tsx`

**Interfaces:**
- Consumes: `startAsk`, `openAskStream` (Task 5), `applyAskEvent`, `emptyAskState`, `loadAsk`, `saveAsk`, `clearAsk`, `AskState` (Task 5). Reuses existing `AnswerView`, `SourcesList`, `FigureGrid`, `LiteratureBlock`, `CitationAudit`, `AskLoader`.

- [ ] **Step 1: Rewrite the Ask component state to drive the stream**

Replace the body of `web/src/pages/Ask.tsx` with a stream-driven version. Key logic:

```tsx
import { useEffect, useRef, useState } from "react"
import { startAsk, openAskStream } from "@/lib/api"
import {
  applyAskEvent, emptyAskState, loadAsk, saveAsk, clearAsk, type AskState, type AskEvent,
} from "@/lib/askStore"
import { Button, Card, Eyebrow } from "@/components/ui"
import AskLoader from "@/components/ask/AskLoader"
import AnswerView from "@/components/ask/AnswerView"
import FigureGrid from "@/components/ask/FigureGrid"
import SourcesList from "@/components/ask/SourcesList"
import LiteratureBlock from "@/components/ask/LiteratureBlock"
import { CitationAudit } from "@/components/ask/CitationAudit"
import { auditSummaryLabel } from "@/lib/askLayout"

const HINTS = [ /* unchanged list */ ]
const TERMINAL = new Set(["done"])

export default function Ask() {
  const [question, setQuestion] = useState("")
  const [state, setState] = useState<AskState | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const stateRef = useRef<AskState | null>(null)        // latest state for the SSE closure
  stateRef.current = state

  // Persist on every state change so a refresh mid-stream loses nothing.
  useEffect(() => { if (state) saveAsk(localStorage, state) }, [state])

  // Restore on mount: rehydrate the last job; if it was still streaming, reconnect at nextIndex.
  useEffect(() => {
    const saved = loadAsk(localStorage)
    if (saved) {
      setState(saved)
      setQuestion(saved.question)
      if (!saved.done) connect(saved.jobId, saved.nextIndex)
    }
    return () => esRef.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function connect(jobId: string, cursor: number) {
    esRef.current?.close()
    const es = openAskStream(jobId, cursor, {
      onEvent: (ev: AskEvent, index: number) => {
        const next = applyAskEvent(stateRef.current ?? emptyAskState(question, jobId), ev, index)
        setState(next)
        if (TERMINAL.has(ev.type) || next.done) es.close()
      },
      onError: () => { /* EventSource auto-retries; nothing to do. The store already has progress. */ },
    })
    esRef.current = es
  }

  async function run(q: string, opts?: { skipDisambiguation?: boolean }) {
    const text = q.trim()
    if (!text) return
    esRef.current?.close()
    clearAsk(localStorage)
    setQuestion(text)
    const { job_id } = await startAsk(text, opts?.skipDisambiguation ?? false)
    const fresh = emptyAskState(text, job_id)
    setState(fresh)
    saveAsk(localStorage, fresh)
    connect(job_id, 0)
  }

  const streaming = !!state && !state.done && state.status === "streaming" && !state.answer
  // ...render: form (unchanged), AskLoader only while `streaming` and no answer yet,
  // then incremental AnswerView/SourcesList/FigureGrid/LiteratureBlock as fields fill,
  // clarification/unavailable/error branches keyed off state.status (reuse existing ResultView markup).
}
```

> Implementation notes for the engineer:
> - Keep the existing `HINTS` array and the `<form>`/header/`aria-live` markup verbatim.
> - Show `<AskLoader />` only until the first `sources`/`answer_delta` arrives (`streaming && !state.answer && state.sources.length === 0`).
> - Render `<AnswerView text={state.answer} />` whenever `state.answer` is non-empty (partial is fine — it's markdown-tolerant); render `<SourcesList citations={state.sources} />` and `<FigureGrid figures={state.figures} />` whenever those arrays are non-empty; `<LiteratureBlock>` when `state.literature`; the collapsed `<details>` CitationAudit when `state.status === "answer"`.
> - For `status === "clarification"` reuse the variants markup, calling `run(v.rewrite || v.label, { skipDisambiguation: true })`.
> - For `status === "unavailable" | "error"` reuse the existing Card markup using `state.reason`.
> - Disable the input/Button while `streaming`.

- [ ] **Step 2: Type-check and build**

Run: `cd web && npm run lint && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 3: Run the web test suite (no regressions)**

Run: `cd web && npx vitest run`
Expected: PASS (existing tests + askStore tests).

- [ ] **Step 4: Manual smoke (real engine)**

Run: `./dev.sh` then in the browser ask a question. Verify: (a) sources/figures appear before the answer finishes; (b) tokens stream in; (c) refresh mid-stream → the partial restores and continues; (d) after completion, refresh → full answer restored with sources/figures; (e) the final restored answer text equals what streamed.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Ask.tsx
git commit -m "feat(web): stream Ask answers with refresh-safe restore"
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- A1 stream tokens → Task 1 (`generate_stream`) + Task 3 (`stream_answer` emits `answer_delta`) + Task 6 (incremental `AnswerView`). ✓
- A1 incremental sources/citations/figures → Task 3 emits `sources`/`figures` before synthesis; Task 6 renders them as they arrive. ✓
- A2 persist in-progress + completed → Task 4 server job log + Task 5 `askStore` localStorage mirror. ✓
- A2 restore on refresh/nav, reflect latest server state → Task 4 cursor replay (daemon keeps generating) + Task 6 mount-restore + reconnect. ✓
- A2 no duplicate tokens/sources/figures → `applyAskEvent` index dedup (Task 5) + authoritative `answer` replace. ✓
- A2 persisted final == streamed final → authoritative `answer` event; variant prefix emitted as first delta so deltas == canonical (Task 3 + Task 5). ✓
- Keep blocking `/api/ask` for batch_ask + tests → Task 4 adds new endpoints only. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. Task 6's render is described as explicit notes mapping to existing components (the engineer reuses verbatim markup already in the file). ✓

**Type consistency:** `generate_stream(system, user, images)` identical across Tasks 1/3. `build_citations`/`build_woven_prompt` signatures identical across Tasks 2/3. Event `type` strings identical across Tasks 3 (emit), 4 (`_serialize_ask_event`), 5 (`AskEvent` union + `applyAskEvent`). `AskState` fields consistent across Tasks 5/6. ✓
