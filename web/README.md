# Neuro·Caseboard — local web console

A single local React site (Vite + React + TypeScript + Tailwind v4 + [react-bits](https://reactbits.dev))
over the **existing** `neuro_caseboard` / `neuro_core` Python engine. The engine stays authoritative —
the web layer imports and forwards to the same functions the CLI and Streamlit app call; it does **not**
reimplement retrieval / RAG / PubMed.

- **No auth.** Anyone who can reach localhost gets in.
- **Local-first.** One command boots everything; no cloud, no Docker.
- **Honest degradation.** If a lane (synthesis / corpus / cards / PubMed) is unavailable, the UI says so
  via `/api/health` — it never fabricates a dossier, citation, or card.

## Architecture

```
api/server.py   FastAPI wrapper (port 8001) — GET /api/health, POST /api/ask, /api/build,
                /api/build/pdf, /api/cards, GET /api/figure  (imports the engine, never reimplements it)
web/            Vite + React + TS SPA (port 5173) — routes: / /ask /build /cards
                dev-proxies /api -> http://127.0.0.1:8001 (one browser origin, no CORS)
```

## Run it

From the repo root:

```bash
./dev.sh
```

or equivalently:

```bash
cd web && npm run dev
```

Then open **http://localhost:5173**. That single command starts the FastAPI engine wrapper
(uvicorn, `--reload`) and the Vite dev server together via `concurrently`.

First-time setup (once): `cd web && npm install`.

> **Port note (WSL2):** the API uses **:8001**, not :8000 — port 8000 sits in a Windows WinNAT
> *excluded port range* on this host and can't be bound from WSL. Override with `API_PORT` (and the
> matching `API_PROXY_TARGET` for Vite) if needed.

## Keys & data (env / engine config)

The web layer adds **no new secrets**. It uses whatever the engine already reads from the environment,
a repo-root `.env`, or `neuro_core/config.py` defaults (resolution order: env → `.env` → defaults):

| Capability | Source | Notes |
|---|---|---|
| Synthesis (Ask/Build) | **Vertex** — `GOOGLE_CLOUD_PROJECT` + Application Default Credentials | `SYNTH_PROVIDER=vertex`, `VERTEX_MODEL`. No Anthropic key needed. |
| Textbook retrieval + figures | `INDEX_DIR`, `ASSETS_DIR` (built LanceDB index) | Required for grounded answers/figures. |
| Corpus PDFs | `CORPUS_DIR` | Only needed to **re-index**, not to query. The dev command defaults it to `/home/michael/textbook_pdfs`. |
| Board-review cards | `cards` table inside `INDEX_DIR` (built from `CARDS_SOURCE_DB`) | Isolated lane; no LLM synthesis. |
| Contemporary literature | `NCBI_API_KEY` (optional) | PubMed works keyless but is rate-limited. |

Check live availability any time: `curl -s localhost:8001/api/health | python3 -m json.tool`,
or just read the **Engine availability** panel on the home page.

Never commit `.env` or keys.

## Surfaces

- **`/ask`** — cited answer from the textbook corpus + a separate Contemporary-Literature `[L#]` block,
  with figures. Calls are slow (~30–80 s); a loader animates real pipeline stages.
- **`/build`** — a structured pre-op dossier (sections → claims with `Why:` + checkbox sub-items →
  figures with claim↔figure links → appendix → evidence summary) and a PDF download.
- **`/cards`** — hybrid search over your personal ABNS / SANS deck; matched cards + media, not synthesized.

## Scripts

```bash
npm run dev      # uvicorn (:8001) + vite (:5173) together
npm run build    # type-check (tsc) + production build
npm run preview  # preview the production build
```
