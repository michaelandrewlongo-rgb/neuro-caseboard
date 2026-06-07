# Local Answer Viewer — Design

**Date:** 2026-06-07
**Status:** Approved (design); pending spec review
**Branch:** `feat/local-viewer`

## Motivation

The `cli/ask.py` pathway works well: good citation-grounded answers with sources
and figure references. The downstream delivery layers (phone PWA, service worker,
Cloudflare tunnel, Cloud Run) accumulated recurring bugs and felt like thrashing.

Almost every painful loop was a property of *remote/phone/cloud delivery*, not of
rendering an answer: the service-worker stale-shell bug (recurred ~3×), the phone
auto-dark "grey shell" saga, the rotating tunnel URL, Cloud Run CPU latency and
GPU quota. None of those can occur on a plain localhost page in a desktop browser.

**Goal:** see `cli.ask` answers — the text *and* the figure images — on a local
webpage. Step back to the simplest thing that works, then build out later.

## Goals

- One page at `http://localhost:8000` in a desktop browser.
- Type a question → see the answer text, the figure images, and the sources.
- Reuse the proven engine seam (`engine.query`) via the existing `/ask` endpoint.
- Dependency-free front end (no CDN, no framework) — stays offline-clean.

## Non-Goals (deliberately deferred)

Phone access, PWA/install, service worker, Cloudflare tunnel, Cloud Run, login/
passcode UX, history, copy/share, and markdown/LaTeX rendering of the answer.
These are not deleted — the existing front end is **archived**, not removed, so any
of them can return in a later stepwise phase.

## Architecture

### Server — barely touched

Keep `server/main.py` as-is, including the endpoints that already work:

- `POST /ask` → `{answer, citations[], figures[]}` (wraps `engine.query`, the same
  seam the CLI uses).
- `GET /figures/{name:path}` → serves a figure PNG (book-relative, percent-encoded,
  containment-guarded).
- `GET /healthz`.

**The only server change:** the static mount at `/` (currently `webapp/`) points to
a new `web/` directory instead.

The passcode middleware stays in place but is **inert locally**: with no
`APP_PASSCODE` in `.env`, the gate passes everything through, so there is no login
on localhost.

Launch with the existing `scripts/serve.sh` (uvicorn; the engine is warmed once on
startup via the lifespan hook, so the first real query isn't slow).

### `/ask` response contract (consumed by the page)

```json
{
  "answer": "string — may contain [n] citation markers and occasional markdown/LaTeX",
  "citations": [{ "n": 1, "book": "...", "chapter": "...", "page": 123 }],
  "figures":   [{ "source_n": 1, "book": "...", "page": 123, "caption": "...", "url": "/figures/<book>/<file>.png" }]
}
```

Each figure already carries a ready-to-use `url`, so the page just sets `<img src>`.

### The page — `web/index.html` + `web/app.js` (+ small inline CSS)

- **Question input + Ask button.** Button disabled and labelled "Searching…" while
  the request is in flight; re-enabled on response or error.
- **Answer block.** Render `answer` as text with line breaks preserved. Turn `[n]`
  markers into clickable links that jump to source *n* in the sources list.
  (Plain text for the MVP — markdown/LaTeX rendering is a clean fast-follow.)
- **Figures.** A column below the answer. Each figure: `<img src={figure.url}>` +
  its `caption` (fallback `"{book}, p.{page}"` when caption is empty) + a
  "Source [n]" label tying it back to `source_n`.
- **Sources.** A numbered list: `[n] {book} — {chapter}, p.{page}`, each with an
  `id` anchor so the `[n]` links in the answer can target it.
- **Error state.** If `/ask` fails, show a plain inline error message; never blank.

No history, no copy/share, no styling beyond clean, readable defaults.

## Data flow

1. User types a question, clicks Ask.
2. `app.js` `POST`s `{question}` to `/ask`, JSON.
3. On success, render `answer`, then `figures` (images), then `citations`.
4. `/figures/...` image requests are served by the existing route from the local
   `assets_dir`. Retrieval and corpus stay entirely local.

## Archive plan

Move `webapp/` → `archive/webapp/` — the PWA shell, `app.js`, `styles.css`,
`sw.js`, `manifest.webmanifest`, and `icons/` all leave together (this includes the
dark theme and the service-worker kill-switch). The cloud/remote scripts
(`scripts/tunnel.sh`, `scripts/setup-wsl-bridge.ps1`, `Dockerfile`, `.dockerignore`,
`.gcloudignore`) are not in the local path and are left in place for a later
cleanup pass — out of scope here to avoid widening the change.

## Reversibility / safety

Pre-existing uncommitted WIP on `master` (service-worker kill-switch, dark theme,
passcode auth, Cloud Run Docker files) was committed as a checkpoint on
`feat/local-viewer` (`23a918e`) **before** any restructuring, so nothing is lost
and the whole effort is reversible by not merging the branch. `master` is untouched.

## Testing

- Existing server tests that assert the static root serves the old PWA shell must be
  updated to expect the new minimal page at `/`.
- Add a smoke test: `GET /` returns the minimal page (200, references the answer
  form / `app.js`).
- Keep the existing `/ask`, `/figures`, `/healthz` tests green (the endpoints are
  unchanged).
- Manual gate: `scripts/serve.sh`, open `http://localhost:8000`, run a real query
  (e.g. an ICA-segments question), confirm the answer text renders, `[n]` links jump
  to sources, and the figure images load.

## Open follow-ups (not now)

Markdown/LaTeX rendering of the answer; archiving the cloud/remote scripts;
re-introducing remote access as a separate deliberate phase.
