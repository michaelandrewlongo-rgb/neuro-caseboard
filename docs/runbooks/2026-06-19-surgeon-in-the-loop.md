# Runbook — Surgeon-in-the-Loop Rehearsal (web)

Closes the gap between "generate a dossier" and a board that **learns the surgeon's operative
preferences** and applies them to future boards.

## Use it
1. `./dev.sh` (or `cd web && npm run dev`) → http://localhost:5173/build. API on :8001.
2. Build a board (e.g. `C5-6 corpectomy`). For a fast offline board, untick **Corpus enrichment**
   and **LLM explorer**.
3. Toggle **Rehearsal mode**. On each claim use **✗ wrong** / **★ important**; add a missing
   consideration per section with **+ missing**.
4. Click **Remember … & update board** → `POST /api/feedback`: the marks distil into profile-keyed
   preferences (stored at `operative-preferences.json`; override via `CASEBOARD_PREFS_STORE`) and the
   board regenerates with them applied. A panel shows how many preferences were remembered.
5. Later builds apply the memory automatically (`/api/build` `use_prefs` defaults on). `GET
   /api/preferences` shows what is remembered — action, pattern, **weight**, and the source cases.

## Guardrails (clinical)
- `add` / `important` apply immediately. A single **wrong** mark only **de-emphasizes** (moves the
  claim to the end of its section); **actual removal requires reinforcement** — the same content
  marked wrong on **≥2 cases** (`weight ≥ 2`). Nothing safety-critical is silently deleted on one
  click. Provenance (weight + source cases) is always visible via `/api/preferences`.
- Memory is keyed by subspecialty **profile** (spine / skull_base / vascular), so a heuristic learned
  on one cervical case carries to the next.
- Decision-support only; verify against primary sources. The interactive surface is the web console;
  the CLI (`caseboard build` / `case`) and the engine default path are unchanged (`prefs`/`use_prefs`
  are opt-in, no-op by default).

## How verified (this PR)
- **Engine + API closed loop** — `tests/rehearsal/` (incl. a FastAPI **TestClient** loop test), plus a
  **real-uvicorn HTTP smoke**: `POST /api/feedback` returns a board carrying the new "missing"
  consideration; `GET /api/preferences` remembers it (`add`, `spine`, `weight 1`); a fresh build of the
  same profile inherits it. 110 scoped tests green.
- **Web** — `cd web && npm run build` (`tsc -b` typecheck + `vite build`) clean.
- **Live browser walkthrough** (the steps above) is the recommended human acceptance check: run
  `./dev.sh` and exercise rehearsal mode end to end.
