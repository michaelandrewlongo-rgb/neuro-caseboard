# Neuro Textbook RAG — Phase 2c: Phone / Web Layer

**Date:** 2026-06-07
**Status:** Design approved; ready for implementation plan.
**Builds on:** Phase 1 (text retrieval + cited synthesis), Phase 2a (figure retrieval), and Phase 2b
(visual retrieval lane), all merged to `master`. The whole pipeline already sits behind one seam —
`engine.query(question) -> QueryResult(answer, citations, figures)`. The current front-ends are a
thin `cli/ask.py` and a minimal local `app/streamlit_app.py` viewer.

## Motivation

The engine answers on-the-job neurosurgery questions with page-exact citations, but today it's only
reachable from the workstation (CLI or a local-only Streamlit page). The goal of Phase 2c is a
**dedicated phone-first web app** so the same answers are usable at the point of need — on rounds, in
the OR lounge — from an iPhone, **without reworking the core**. It attaches at the existing
`engine.query` seam.

## Decisions (locked during brainstorming)

- **Retrieval stays local; only synthesis is cloud.** The GPU embeddings, reranker, BiomedCLIP, the
  142 MB LanceDB index, and the copyrighted textbook corpus remain on the WSL2 workstation. The data
  boundary is unchanged: the only things crossing the network are (a) retrieved excerpts + figure
  page images sent to the synthesis model (exactly as today) and (b) the rendered answer sent to the
  user's own phone over a private tailnet. (Rejected: cloud-hosted GPU engine — burns the $200 GCP
  credit fast and moves the copyrighted corpus + index off-box.)
- **Availability = "PC-on is fine."** The phone works when the workstation is awake; it does **not**
  need to answer while the PC is off. This is what keeps everything local and free.
- **Synthesis moves to Vertex AI, model `gemini-2.5-pro`.** Up from `gemini-3-flash-preview`
  (OpenRouter). Routing through Vertex puts the (pennies-per-question) synthesis cost on the user's
  **$200 Google Cloud credit** — effectively free at personal volume. Gemini 2.5 Pro is GA, stable,
  multimodal (handles the figure images), and a clear reasoning step up from Flash over conflicting
  sources. (Rejected: Gemini 3 Pro preview — preview-tier instability; Claude Sonnet 4.6 — slightly
  pricier, Gemini Pro is enough here.)
- **Front-end = dedicated phone-first PWA.** A small FastAPI server wraps `engine.query` and serves a
  responsive, one-handed single-page app, installable to the iPhone home screen (full-screen, native
  feel). (Rejected: mobile-tuned Streamlit — clunky on phones, full-page reruns, not app-like.)
- **Answer screen = Layout A (single scroll, all inline).** Pinned ask box → answer with tappable
  `[n]` citation chips → inline figures (tap = full-screen) → full source list, one continuous
  scroll. Chosen over a compact/collapsible layout because, for a glance-and-go reference, seeing the
  citations without hunting for a tap target matters more than a tidy screen.
- **Access = Tailscale (already installed on the Windows host).** A private mesh VPN — only the
  user's enrolled devices can reach the app; no public URL. (Rejected: Cloudflare Tunnel + Access —
  unneeded public exposure for a single-user tool.)
- **v1 extras: question history + copy/share.** History is stored client-side (localStorage), so the
  server stays stateless (no DB). (Deferred: streaming answers, voice input — easy to add later at
  the same seam.)
- **No extra app passcode in v1.** The tailnet is already private and single-user; auth is handled at
  the network layer by Tailscale. An app-level passcode is a one-line future add.

## Architecture & data flow

```
  iPhone (PWA, home-screen icon)
        │  POST /ask {question}  over Tailscale
        ▼
  Windows host  ──[Tailscale IP]──►  netsh portproxy + firewall allow   (WSL2 bridge)
        │
        ▼
  WSL2: FastAPI server (long-running; models loaded ONCE at startup → kept warm)
        │  engine.query(question)        ← unchanged seam
        ▼
  Local GPU retrieval → excerpts + figure page PNGs   (on-disk, $0 marginal)
        │
        ▼
  Synthesis → Vertex AI  gemini-2.5-pro   (only excerpts + figure images leave)
        │
        ▼
  FastAPI → JSON {answer, citations[], figures[]}; figure PNGs via /figures route
        │
        ▼
  Phone renders Layout A
```

**The WSL2 ↔ Tailscale bridge.** The engine runs in WSL2 (NAT'd network); Tailscale runs on Windows.
A remote device hitting the Windows Tailscale IP on the server port must be forwarded to the WSL2
service. A one-time `netsh interface portproxy` rule (plus a Windows Firewall allow rule) bridges
`0.0.0.0:<port>` on Windows → `<wsl2-ip>:<port>`. Provided as `scripts/setup-wsl-bridge.ps1`.

**Why a long-running server, not the CLI.** Each CLI invocation reloads BGE / reranker / CLIP
(~tens of seconds). The FastAPI process loads them once via the existing `get_engine()` global cache
and stays warm, so each request is just retrieval (fast, GPU) + the Gemini call (a few seconds).

## Components

```
server/
  __init__.py
  main.py        # FastAPI app; startup hook warms the engine via get_engine();
                 #   routes; mounts webapp/ static + figure assets
  schemas.py     # Pydantic: AskRequest, AskResponse, CitationOut, FigureOut
webapp/                              # static PWA, served by FastAPI
  index.html     # Layout A single-page shell + persistent disclaimer
  app.js         # ask → render; question history (localStorage); copy/share
  styles.css
  manifest.webmanifest               # name, icons, display:standalone
  sw.js                              # service worker: caches app shell (install/offline shell)
  icons/                             # home-screen icons
scripts/
  serve.sh                          # uvicorn server.main --host 0.0.0.0 --port 8000
  setup-wsl-bridge.ps1              # one-time Windows: netsh portproxy + firewall allow
tests/
  test_server.py                    # API contract tests, engine.query mocked
```

`engine/` is **not modified**. The existing `cli/ask.py` and `app/streamlit_app.py` remain as-is.

## API contract

| Route | Method | Behavior |
|---|---|---|
| `/` | GET | Serves the PWA shell (`webapp/index.html`); static assets mounted alongside. |
| `/ask` | POST | Body `{ "question": str }` → `{ answer, citations[], figures[] }`. Calls `engine.query()` unchanged. |
| `/figures/{name}` | GET | Serves a rendered figure PNG (read-only mount of the existing assets dir). Reachable only over the tailnet. 404 on unknown name. |
| `/healthz` | GET | `{ "warm": bool }` — whether the engine's models are loaded. Drives the "warming up" UI state. |

**Response mapping (1:1 from today's `QueryResult`):**
- `answer`: markdown string (unchanged engine output).
- `citations[]`: `{ n, book, chapter, page }`.
- `figures[]`: `{ source_n, book, page, caption, url }` — same fields as today plus `url`
  (`/figures/<name>`) in place of the local `image_path`.

## Screen states (Layout A)

- **Loading** — spinner while `/ask` runs (just the Gemini call; engine is warm).
- **Refusal** — when the engine returns *"Not found in the provided sources."*, render it verbatim as
  the answer with no figures/sources. The honest-abstention path is preserved, never shown as an
  error.
- **Error** — network/server failure (PC asleep, Tailscale off, Vertex auth expired) → friendly
  "Can't reach the textbook server — is your workstation awake and Tailscale connected?" + Retry.
- **Warming** — request before models finish loading → brief "warming up…" state driven by
  `/healthz`.

## Security / data boundary

- Books, embeddings, and the index never leave WSL2 (unchanged).
- Figure PNGs are copyrighted page images served **only to the user's own device over the tailnet** —
  identical exposure to today's local Streamlit viewer.
- The engine's cite-only / refuse-otherwise system prompt is untouched.
- Network auth is Tailscale device enrollment; no public surface.
- The "Decision-support only" disclaimer is persistent on screen.

## Validation gates (proven before integration)

- `tests/test_server.py` (engine.query **mocked**): `/ask` returns the documented schema; a refusal
  string passes through verbatim with empty figures/sources; `/figures` serves a known file and 404s
  on an unknown name; `/healthz` reflects warm state.
- Existing **37 engine tests stay green** (no `engine/` changes).
- **Provider-switch validation** (same bar used when adopting Gemini Flash): run a handful of
  in-domain clinical queries through the new Vertex `gemini-2.5-pro` path and confirm answers are
  factually correct, every claim cited, source disagreements flagged, and the refusal path still
  fires on a deliberately off-domain query.
- Manual e2e: `serve.sh` in WSL2 → run `setup-wsl-bridge.ps1` on Windows → open from the phone over
  Tailscale → ask a real question → confirm Layout A renders (answer + figures + sources), figures
  open full-screen, history + copy/share work, and the app installs to the home screen.

## Configuration & cost

- `SYNTH_PROVIDER=vertex`, synthesis model `gemini-2.5-pro`, `GOOGLE_CLOUD_PROJECT=<project>`, plus a
  one-time `gcloud auth application-default login`.
- Server host/port (default `0.0.0.0:8000`).
- Cost: retrieval is local ($0 marginal). Synthesis is pennies-to-low-cents per question on
  `gemini-2.5-pro`, billed to the $200 GCP credit — effectively free at personal volume.

## Out of scope (documented future refinements)

- Streaming answers (token-by-token) and voice input — deferred; attach at the same seam.
- Always-on availability (cloud-hosted engine) — explicitly rejected for the data boundary + cost.
- App-level passcode / multi-user auth — not needed for a single-user tailnet tool.
- Server-side history sync across devices — v1 history is client-side localStorage only.

## Known limitations carried forward

- Index build still isn't crash-resumable (re-embeds from scratch; unchanged by this phase).
- The source list still shows all retrieved passages, not only the ones the model cited inline
  (unchanged engine behavior; surfaced as-is in the UI).
