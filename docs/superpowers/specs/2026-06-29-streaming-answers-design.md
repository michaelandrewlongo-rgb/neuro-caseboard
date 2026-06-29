# Streaming Answers — Design

**Branch:** `streaming-answers` (the literal "streaming answers" is not a valid git ref — spaces disallowed)
**Date:** 2026-06-29
**Scope:** Ask pathway only (Build/Cards/Briefing unchanged).

## Problem

`POST /api/ask` is a single blocking call that returns one JSON blob after the *entire*
pipeline finishes (~2 min): disambiguation → retrieval → figure collection → the full
synthesis `generate()` (long pole) → literature lane → entailment verification. Nothing
reaches the UI until everything is done, and refreshing / navigating away discards all
progress (`Ask.tsx` is unmounted by the router; no persistence).

## Goals (from the request)

- **A1 Stream:** answer tokens appear shortly after submit; sources/citations/figures appear
  incrementally as retrieved; no waiting for the whole pipeline.
- **A2 Persist:** refreshing / tab-change / navigation does not lose progress; the in-progress
  *and* completed response are restored from the latest **server-side** state; no duplicate
  tokens / sources / figures; persisted final answer exactly matches the streamed one.

## Architecture

One new idea: an Ask request becomes a **job** the server owns, exposed as a replayable
**SSE event log**. The client is a thin reducer over that log with a `localStorage` mirror.

```
POST /api/ask {question, skip_disambiguation}
    → create AskJob, spawn daemon thread running stream_answer(), return {job_id}  (instant)

GET  /api/ask/stream/{job_id}?cursor=N   (SSE)
    → replay job.events[N:] as they appear, tail live until a `done` event, then close
```

### Server-side job (api/server.py)

- `_ASK_JOBS: dict[str, AskJob]`, LRU-capped at 8 (mirrors the existing `_DOSSIER_CACHE`).
- `AskJob`: `id`, append-only `events: list[dict]`, `done: bool`, a `threading.Lock`.
  Each event is a JSON-ready dict with a `type`. `emit(event)` appends under the lock.
- `run_ask_job(job, question, skip_disambiguation)` runs in a **daemon thread** (the pipeline
  is synchronous) and calls `stream_answer(..., emit=job.emit)`. Generation is decoupled from
  any HTTP connection, so it keeps running while the client is away — this is what makes
  "reflects the latest server-side state" true.
- SSE endpoint = async generator that yields `id: {i}\ndata: {json}\n\n` for `events[cursor:]`,
  sleeping ~50 ms when caught up, until it has emitted a `done` event.
  `# ponytail: poll loop, swap for a threading.Condition if concurrency ever matters`
  (single-user local tool — invisible).

### Event types (the wire protocol)

| type | payload | when |
|------|---------|------|
| `sources` | `{citations: Citation[]}` | right after retrieval, before synthesis |
| `figures` | `{figures: Figure[]}` | right after retrieval |
| `answer_delta` | `{text: str}` | per synthesis token chunk |
| `answer` | `{answer, citations, figures, refusal: bool}` | **authoritative** final; client replaces text+sources+figures with these |
| `literature` | `{literature: Literature \| null}` | when Lane B finishes |
| `verification` | `{verification}` | after the full answer is verified |
| `clarification` | `{question, variants}` | ambiguous query (terminal, then `done`) |
| `unavailable` | `{reason}` / `error` `{error}` | GPU-not-ready / engine error (terminal) |
| `done` | `{}` | always last; marks the job complete |

The `answer` event is the single source of truth for the final state. Normally its
citations/figures equal what was streamed early; on a **refusal** they are empty (parity with
today's `_answer`, which drops spurious sources on abstention). The client *replaces* (never
appends) on `answer`, so reconciliation is dedup-safe and the persisted final exactly matches.

The variant prefix (`**Assuming X …**`) is emitted as the **first** `answer_delta` (the variant
is known pre-synthesis), so accumulated deltas == canonical final with no visible "jump".

### Streaming orchestrator (neuro_caseboard/qa_stream.py — new)

`stream_answer(question, emit, *, config=None, force=False, skip_disambiguation=False)`:

1. `bundle = engine.retrieve_for_synthesis(question, skip_disambiguation=...)`
   - `Clarification` → `emit(clarification)`, `emit(done)`, return.
2. Build citations from `bundle.hits` (+ appended figures) — the same construction `synthesize()`
   does today, factored into a shared `build_citations(hits, figures)` helper. `emit(sources)`,
   `emit(figures)`.
3. Start Lane B (`build_literature_section`) in a worker thread (concurrent, failure-safe → None).
4. If a variant was chosen, `emit(answer_delta)` with the "Assuming …" prefix.
5. Build the synthesis prompt (reuse `synthesize`'s prompt assembly, factored into
   `build_synth_prompt(question, hits, figures, variant_directive)`), then iterate
   `synth_client.generate_stream(system, user, images)`, `emit(answer_delta)` per chunk,
   accumulating `answer`.
6. Empty-answer guard + refusal handling (parity with `_answer`): if empty after one retry →
   canonical `REFUSAL`; if refusal → drop citations/figures. `emit(answer, refusal=…)`.
7. Join Lane B → `emit(literature)`. `verify_answer(full_answer, premises)` → `emit(verification)`.
8. `emit(done)`.

**Fallback:** woven mode (`LITERATURE_WEAVE`) or any exception in the streaming path → call the
existing blocking `answer_question()` and emit `sources`/`figures`/`answer`/`literature`/
`verification` as one batch, then `done`. Weave keeps working (un-streamed); persistence still
applies to it. Keeps the streaming diff focused on the default path.

### Synth clients (neuro_core/synth_clients.py)

Add `generate_stream(system, user, images)` yielding text deltas:
- `OpenRouterSynthClient` / `LocalSynthClient`: `chat.completions.create(stream=True)`,
  yield `chunk.choices[0].delta.content`.
- `VertexSynthClient`: `models.generate_content_stream(...)`, yield `chunk.text`.
- Default fallback (base method): `yield self.generate(system, user, images)` once — any client
  without real streaming still works end-to-end.

`# ponytail:` the `analyze`/disambiguation client stays non-streaming (it's a one-shot
classification, not user-visible prose).

### Web client

- `web/src/lib/askStore.ts` — `localStorage` mirror `{ question, jobId, status, answer,
  sources, figures, literature, verification, nextIndex, kind }`. Save on every event; load on
  mount. (Same shape/pattern as `reviewStore.ts`.)
- `web/src/lib/api.ts` — `startAsk(question, opts) → {jobId}` (POST) and an `openAskStream(jobId,
  cursor, handlers)` using **`EventSource`** (`GET …/stream/{jobId}?cursor=N`). EventSource gives
  native auto-reconnect; the client tracks `nextIndex` and **ignores any event with index <
  nextIndex** (belt-and-suspenders dedup on top of the cursor).
- `web/src/pages/Ask.tsx`:
  - submit → clear store → `startAsk` → save jobId → `openAskStream(jobId, 0, …)` → reduce
    events into React state, persisting each.
  - mount → if the store has a job: restore state immediately; if `status` not terminal,
    `openAskStream(jobId, nextIndex, …)` to continue from where it left off.
  - render the answer incrementally (`AnswerView` with partial text); `SourcesList` / `FigureGrid`
    fill in as their events arrive; the existing `AskLoader` shows only until the first event.

## Data flow / dedup invariants

- Server events are an **append-only indexed log**; the client's `nextIndex` is the only cursor.
- Reconnect always resumes at `nextIndex`; events `< nextIndex` are dropped → no dup tokens/
  sources/figures.
- The terminal `answer` event is authoritative; the client *replaces* text+sources+figures →
  persisted final == streamed final, exactly.

## Error handling

- Engine error / GPU-not-ready inside the job → `emit(unavailable|error)` then `done`
  (same shapes the current `/api/ask` returns, so `Ask.tsx`'s existing `ResultView` branches are
  reused). Lane B failure → `literature: null` (unchanged behavior). SSE for an unknown
  `job_id` → 404; the client then re-submits.
- Job lost to a server restart mid-stream (in-memory store): the stream GET 404s; the client
  treats it as "expired" and offers to re-ask. Acceptable ceiling for a single-user tool.

## Testing

- **synth_clients:** `generate_stream` yields deltas that concatenate to `generate`'s text
  (fake OpenAI/genai stream objects); default fallback yields the whole string once.
- **stream_answer:** with injected engine + fake streaming client + emit-collector, assert the
  event order (`sources` before any `answer_delta`, `answer` authoritative, `done` last),
  refusal drops sources/figures, Clarification short-circuits, woven/exception → batch fallback.
- **server:** `POST /api/ask` returns a `job_id`; the SSE endpoint replays from `cursor` and is
  idempotent across two connects (no duplicate events); unknown job → 404.
- **web (vitest):** `askStore` round-trips; the Ask reducer ignores `index < nextIndex` (dedup)
  and adopts the authoritative `answer` event; restore-on-mount rehydrates state.

## Out of scope (YAGNI)

- Disk-persisted / multi-process job store (single-user, in-memory is enough).
- Streaming Build/Cards/Briefing.
- Streaming the woven path token-by-token (batch fallback covers it).
- Cancel-job server endpoint (closing the EventSource is enough; the daemon thread finishes
  into the cache harmlessly).
