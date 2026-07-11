# Decision Card SP0 — Evidence-span & folio transport — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop dropping the already-computed `evidence_spans` sidecar and the openable folio at the API boundary — serialize both onto the `/api/ask` blocking response and the SSE stream, and expose them in the web wire types.

**Architecture:** Pure additive transport. `qa.py` already builds `QAResult.evidence_spans` (behind `EVIDENCE_SPANS`); `neuro_core.Citation` already carries `printed_page` + `page_ref()`. This plan (1) serializes spans into the blocking response, (2) exposes the folio in `_citation_dict`, (3) computes + emits an `evidence` SSE event on the streaming path, and (4) declares the wire types in `api.ts`. No behavior change; every field degrades to empty/`None` when absent. The Decision Card gate (SP1) and render (SP2) are separate plans.

**Tech Stack:** FastAPI + Starlette SSE (`api/server.py`), Python dataclasses (`neuro_caseboard/qa_stream.py`, `evidence_spans.py`), Vite/TypeScript + Vitest (`web/src/lib`).

## Global Constraints

- **Additive & failure-safe.** A missing/empty field serializes to `[]` or `None`; never raise, never block or blank an answer. (Mirrors `evidence_spans.extract_and_verify` returning `[]` on any failure.)
- **Flag-gated, default OFF.** Span computation stays behind `EVIDENCE_SPANS` (env truthy = `1|true|yes|on`). Do NOT flip its default. No existing default (`EVIDENCE_SPANS`, `PROMPT_DECISION_FURNITURE`, `CORPUS_RETRIEVAL`) is changed in this plan.
- **No new paid LLM call.** The streaming task reuses the same `extract_and_verify` pass `qa.py` already runs; it adds zero calls when `EVIDENCE_SPANS` is off, and one extraction call when on (identical to the blocking path).
- **Folio is additive, not a replacement.** Add `printed_page` + `page_ref`; keep `page` and `location` unchanged for back-compat. The UI switches to `page_ref` in SP2.
- **Server-side content stays server-side.** Serialize the `EvidenceSpan.quote` (it IS what the reader opens) but NOT full chunk text (parity with the `[D#]` corpus lane, whose passage content is deliberately withheld from the wire).
- **Test scope discipline (CLAUDE.md).** New tests import-guard `fastapi` with `pytest.importorskip("fastapi")` at module top (required `.[dev]` CI has fastapi as core, but the guard matches the repo's existing `test_api_ask_*` pattern and keeps collection safe).

---

## File Structure

- **Modify `api/server.py`**
  - Add `_evidence_spans_list(spans) -> list` serializer (near `_corpus_list`, ~line 400).
  - Add `"evidence_spans"` to the `/api/ask` blocking response dict (~line 555).
  - Enrich `_citation_dict` with `printed_page` + `page_ref` (~line 328).
  - Add an `"evidence"` case to `_serialize_ask_event` (~line 433).
- **Modify `neuro_caseboard/qa_stream.py`**
  - After the `verification` emit (~line 169), emit an `evidence` event, flag-gated on `EVIDENCE_SPANS`, reusing the in-scope `synth_client` + `premises`.
- **Modify `web/src/lib/api.ts`**
  - Add `EvidenceSpan` interface; add `evidence_spans` to the answer variant of `AskResponse`; add `printed_page?`/`page_ref?` to `Citation`.
- **Tests**
  - Create `tests/test_api_ask_evidence_spans.py` (blocking response + folio in `_citation_dict`).
  - Modify `tests/test_api_ask_stream.py` (evidence event serializes).
  - Modify `web/src/lib/api.test.ts` (answer response parses `evidence_spans`).

---

### Task 1: Serialize `evidence_spans` on the blocking `/api/ask` response

**Files:**
- Modify: `api/server.py` (add `_evidence_spans_list` near line 400; add field to response dict ~line 555)
- Test: `tests/test_api_ask_evidence_spans.py` (create)

**Interfaces:**
- Consumes: `neuro_caseboard.qa.QAResult.evidence_spans: list[EvidenceSpan]`; `EvidenceSpan(claim, marker, quote, matched, score)` from `neuro_caseboard.evidence_spans`.
- Produces: `_evidence_spans_list(spans) -> list[dict]` with keys `claim, marker, quote, matched, score`; `/api/ask` answer body gains `"evidence_spans": list`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_ask_evidence_spans.py
"""SP0: the /api/ask response and the citation dict must carry the §3.3 sidecar + folio."""
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402


def test_api_ask_carries_evidence_spans(monkeypatch):
    import api.server as server
    from neuro_caseboard.qa import QAResult
    from neuro_caseboard.evidence_spans import EvidenceSpan

    fake = QAResult(
        answer="Claim [1].", citations=[], figures=[], literature=None,
        evidence_spans=[EvidenceSpan(claim="Claim [1].", marker="1",
                                     quote="the verbatim sentence", matched=True, score=1.0)])
    monkeypatch.setattr("neuro_caseboard.qa.answer_question", lambda *a, **k: fake)

    body = TestClient(server.app).post("/api/ask", json={"question": "q"}).json()
    assert body["kind"] == "answer"
    assert body["evidence_spans"] == [{
        "claim": "Claim [1].", "marker": "1",
        "quote": "the verbatim sentence", "matched": True, "score": 1.0}]


def test_api_ask_evidence_spans_empty_when_absent(monkeypatch):
    import api.server as server
    from neuro_caseboard.qa import QAResult

    fake = QAResult(answer="Plain answer.", citations=[], figures=[], literature=None)
    monkeypatch.setattr("neuro_caseboard.qa.answer_question", lambda *a, **k: fake)
    body = TestClient(server.app).post("/api/ask", json={"question": "q"}).json()
    assert body["evidence_spans"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_ask_evidence_spans.py -v`
Expected: FAIL with `KeyError: 'evidence_spans'`.

- [ ] **Step 3: Add the serializer**

In `api/server.py`, immediately after `_corpus_list` (~line 401):

```python
def _evidence_spans_list(spans) -> list:
    """Serialize the §3.3 quoted-span sidecar. Each span is the model's verbatim supporting
    sentence + whether it string-matched its cited chunk (precision-1.0 fabrication check). The
    quote IS display copy here (unlike corpus content) — it is what the reader opens on a click."""
    out = []
    for s in spans or []:
        out.append({
            "claim": getattr(s, "claim", ""),
            "marker": getattr(s, "marker", ""),
            "quote": getattr(s, "quote", ""),
            "matched": bool(getattr(s, "matched", False)),
            "score": getattr(s, "score", 0.0),
        })
    return out
```

- [ ] **Step 4: Add the field to the response dict**

In the `/api/ask` handler `return {...}` (~line 555), add after the `"verification"` line:

```python
        "evidence_spans": _evidence_spans_list(getattr(result, "evidence_spans", None)),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_api_ask_evidence_spans.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add api/server.py tests/test_api_ask_evidence_spans.py
git commit -m "feat(decision-card/sp0): serialize evidence_spans onto /api/ask"
```

---

### Task 2: Expose the folio (`printed_page` + `page_ref`) in `_citation_dict`

**Files:**
- Modify: `api/server.py` (`_citation_dict`, ~line 328)
- Test: `tests/test_api_ask_evidence_spans.py` (add one test)

**Interfaces:**
- Consumes: `neuro_core.synthesize.Citation` fields `printed_page: str` and method `page_ref() -> str` (returns `"p.<folio>"` when known, else `"p.<pdf> (pdf)"`).
- Produces: every `_citation_dict` gains `"printed_page": str` and `"page_ref": str | None`. `page`/`location` unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_ask_evidence_spans.py`:

```python
def test_citation_dict_exposes_folio():
    import api.server as server
    from neuro_core.synthesize import Citation

    c = Citation(n=1, book="Youmans", chapter="Ch419", page=5710, text="body",
                 printed_page="3357")
    d = server._citation_dict(c)
    assert d["printed_page"] == "3357"
    assert d["page_ref"] == "p.3357"
    assert d["page"] == 5710          # back-compat field unchanged


def test_citation_dict_folio_absent_is_pdf_marked():
    import api.server as server
    from neuro_core.synthesize import Citation

    c = Citation(n=1, book="B", chapter="C", page=42, text="t")   # printed_page defaults ""
    d = server._citation_dict(c)
    assert d["printed_page"] == ""
    assert d["page_ref"] == "p.42 (pdf)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_ask_evidence_spans.py -k folio -v`
Expected: FAIL with `KeyError: 'printed_page'`.

- [ ] **Step 3: Enrich `_citation_dict`**

Replace the `_citation_dict` body (~line 328) with:

```python
def _citation_dict(c) -> dict:
    book = getattr(c, "book", "")
    chapter = getattr(c, "chapter", "") or ""
    page = getattr(c, "page", None)
    printed_page = getattr(c, "printed_page", "") or ""
    page_ref = getattr(c, "page_ref", None)   # Citation.page_ref is a @property (str), not a method
    return {
        "n": getattr(c, "n", None),
        "book": book,
        "chapter": chapter,
        "page": page,
        "printed_page": printed_page,   # the folio a reader can actually open ("" when unrecoverable)
        "page_ref": page_ref,           # display string: "p.3357" or "p.42 (pdf)"
        "location": _citation_location(book, chapter, page),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_ask_evidence_spans.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Guard against a stream-test regression**

Run: `pytest tests/test_api_ask_stream.py -v`
Expected: PASS (the added keys are additive; `sources[...]["book"]` assertions still hold).

- [ ] **Step 6: Commit**

```bash
git add api/server.py tests/test_api_ask_evidence_spans.py
git commit -m "feat(decision-card/sp0): expose printed_page + page_ref in citation dict"
```

---

### Task 3: Compute + stream the `evidence` SSE event

**Files:**
- Modify: `neuro_caseboard/qa_stream.py` (after the `verification` emit, ~line 169)
- Modify: `api/server.py` (`_serialize_ask_event`, ~line 433)
- Test: `tests/test_api_ask_stream.py` (add one test)

**Interfaces:**
- Consumes: in-scope `synth_client`, `full_answer`, `premises` (qa_stream ~line 118/138/163); `extract_and_verify(answer, premises, synth_client) -> list[EvidenceSpan]`.
- Produces: an SSE event `{"type": "evidence", "evidence_spans": [...]}` serialized via `_evidence_spans_list`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_ask_stream.py`:

```python
def test_evidence_event_serializes(monkeypatch):
    """An 'evidence' domain event → JSON spans on the wire (quote is display copy)."""
    import api.server as server
    from neuro_caseboard.evidence_spans import EvidenceSpan

    def fake(question, emit, **kwargs):
        emit({"type": "evidence", "evidence_spans": [
            EvidenceSpan(claim="c [1]", marker="1", quote="q", matched=True, score=1.0)]})
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", fake)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    events = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=0").text)
    ev = next(e for e in events if e["type"] == "evidence")
    assert ev["evidence_spans"][0]["quote"] == "q"
    assert ev["evidence_spans"][0]["matched"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_ask_stream.py::test_evidence_event_serializes -v`
Expected: FAIL — the raw `EvidenceSpan` isn't JSON-serializable / no `evidence` event handler, so the SSE payload lacks a matching event.

- [ ] **Step 3: Serialize the `evidence` event**

In `api/server.py` `_serialize_ask_event`, add before the final `# unavailable / error / done pass through` comment (~line 456):

```python
    if t == "evidence":
        return {"type": "evidence",
                "evidence_spans": _evidence_spans_list(ev.get("evidence_spans"))}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_ask_stream.py::test_evidence_event_serializes -v`
Expected: PASS.

- [ ] **Step 5: Emit the event from the streaming orchestrator**

In `neuro_caseboard/qa_stream.py`, confirm `import os` is present at the top of the module (add it if missing). Then, between the `verification` emit and the `done` emit (~line 169–170), insert:

```python
        if os.environ.get("EVIDENCE_SPANS", "").lower() in ("1", "true", "yes", "on"):
            from neuro_caseboard.evidence_spans import extract_and_verify
            emit({"type": "evidence",
                  "evidence_spans": extract_and_verify(full_answer, premises, synth_client)})
```

- [ ] **Step 6: Run the streaming suite**

Run: `pytest tests/test_api_ask_stream.py -v`
Expected: PASS (all, including the pre-existing idempotency + corpus tests — the new emit is flag-gated OFF by default, so the untouched tests see no extra event).

- [ ] **Step 7: Commit**

```bash
git add api/server.py neuro_caseboard/qa_stream.py tests/test_api_ask_stream.py
git commit -m "feat(decision-card/sp0): compute + stream the evidence SSE event"
```

---

### Task 4: Declare the wire types in `api.ts`

**Files:**
- Modify: `web/src/lib/api.ts` (`Citation` interface ~line 61; `AskResponse` answer variant ~line 102)
- Test: `web/src/lib/api.test.ts` (add one test)

**Interfaces:**
- Consumes: the JSON shapes produced by Tasks 1–3.
- Produces: `EvidenceSpan` TS interface; `Citation` gains `printed_page?: string; page_ref?: string | null`; the answer variant of `AskResponse` gains `evidence_spans: EvidenceSpan[]`.

- [ ] **Step 1: Write the failing test**

Append to `web/src/lib/api.test.ts` (inside a new `describe`):

```typescript
import type { AskResponse } from "./api"

describe("Ask answer wire type", () => {
  it("accepts evidence_spans + citation folio fields", () => {
    const r: AskResponse = {
      kind: "answer",
      answer: "Claim [1].",
      citations: [{ n: 1, book: "Youmans", chapter: "Ch419", page: 5710,
                    printed_page: "3357", page_ref: "p.3357", location: "Youmans, Ch419, p.5710" }],
      figures: [],
      literature: null,
      evidence_spans: [{ claim: "Claim [1].", marker: "1", quote: "the sentence",
                         matched: true, score: 1.0 }],
    }
    // Runtime assertions so the test exercises the value, not just the type.
    expect(r.kind === "answer" && r.evidence_spans[0].matched).toBe(true)
    expect(r.kind === "answer" && r.citations[0].page_ref).toBe("p.3357")
  })
})
```

- [ ] **Step 2: Run the type-checker to verify it fails**

Run: `cd web && npx tsc -b`
Expected: FAIL — 3 errors: `printed_page`/`page_ref` not on `Citation`, `evidence_spans` not on the
answer variant. (NOTE: `vitest run` alone will NOT fail here — it transpiles without type-checking,
so the type gate is `tsc -b`, which is what `npm run build` uses.)

- [ ] **Step 3: Add the `EvidenceSpan` interface and extend `Citation`**

In `web/src/lib/api.ts`, add near the other interfaces (after `Citation`, ~line 68):

```typescript
export interface EvidenceSpan {
  claim: string
  marker: string   // "1" | "L3" | "D2" — the [n]/[L#]/[D#] this claim cited
  quote: string    // the model's verbatim supporting sentence (what the reader opens)
  matched: boolean // did the quote string-match its cited chunk (precision-1.0 fabrication check)
  score: number
}
```

Extend the `Citation` interface (~line 61) with two optional fields:

```typescript
  printed_page?: string        // the openable folio ("" when unrecoverable)
  page_ref?: string | null     // display string: "p.3357" or "p.42 (pdf)"
```

- [ ] **Step 4: Extend the `AskResponse` answer variant**

Replace the answer variant (~line 102):

```typescript
  | { kind: "answer"; answer: string; citations: Citation[]; figures: Figure[];
      literature: Literature | null; evidence_spans: EvidenceSpan[] }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run src/lib/api.test.ts`
Expected: PASS.

- [ ] **Step 6: Lint + full web unit run (no regressions)**

Run: `cd web && npm run lint && npm run test`
Expected: PASS (eslint clean; all vitest suites green).

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/api.test.ts
git commit -m "feat(decision-card/sp0): declare evidence_spans + folio in Ask wire types"
```

---

## Self-Review

**Spec coverage (SP0 slice of §6 Transport):**
- Serialize `evidence_spans` on `/api/ask` → Task 1. ✓
- Serialize on the stream → Task 3. ✓
- Expose folio (`printed_page`) in citation dict → Task 2. ✓
- Wire types → Task 4. ✓
- Page-image URL + full chunk `text` → **deliberately deferred** to SP2 (no per-page asset exists yet; text stays server-side). Noted in Global Constraints, not a gap.
- `decision_card` field → **not in SP0** (the field doesn't exist until SP1). Correct.

**Placeholder scan:** No TBD/TODO; every code step shows actual code; every run step shows the exact command + expected result. ✓

**Type consistency:** `_evidence_spans_list` keys (`claim, marker, quote, matched, score`) match `EvidenceSpan` (Python dataclass and TS interface) across Tasks 1, 3, 4. `page_ref`/`printed_page` names match across Tasks 2 and 4. ✓

---

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, two-stage review between tasks.
2. **Inline Execution** — execute the four tasks in this session with checkpoints.

Given SP0 is four small additive tasks in files the session already understands, inline execution with a commit-per-task checkpoint is the lazy fit; subagent-driven is the safer fit if parallel review is wanted.
