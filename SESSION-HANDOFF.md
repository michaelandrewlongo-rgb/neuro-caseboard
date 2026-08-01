# Session handoff — neuro-caseboard (2026-06-29)

Resume point for a fresh session. Everything below is verified at write time, not recalled.

## TL;DR
- **master is in sync** (local == origin) at **`07fa48f`**; CI green.
- Working branch checked out in the main repo is still **`eval/literature-rewrite-arm`** (your eval work — untouched all session).
- The **live GUI is up on glm** at **http://localhost:8001** and publicly at a Cloudflare tunnel (URL below).
- 4 PRs merged this session (#84–#87). 1 PR still open (#79).

## What shipped this session (all merged to master)
| PR | What | Squash |
|----|------|--------|
| #84 | Architecture docs (`docs/NEURO_CASEBOARD_ARCHITECTURE.md` + `DIAGRAMS.md`) committed & corrected to the glm default; README gained an "Ask synthesis model" section | `2c6b2ba` |
| #85 | `OpenRouterSynthClient` retries **text-only** when the model rejects figure images (glm-5.2 is text-only → was 500-ing on figure queries) | `aed10fd` |
| #86 | `/api/health` `_probe_synth` now probes the **configured** provider (openrouter/local), not just vertex — was falsely reporting `synth:false` for glm | `fdc0229` |
| #87 | docker-compose Ask synthesis flipped **vertex → openrouter glm-5.2**; `openai` promoted to a **core** dependency (was undeclared); Vertex kept for Build/briefing | `07fa48f` |

Also done: synced local master (was 17 behind), pruned 18 stale local branches + their state, generated `docs/ask-pathway-llm-calls.{svg,png}` (Ask data-flow figure), spun up the Cloudflare tunnel.

## Live runtime (these are detached — survive session end)
- **App server**: bare uvicorn, **PID 417228**, `0.0.0.0:8001`, `SYNTH_PROVIDER=openrouter` (glm-5.2 synth + gemini-3.1-flash-lite disambig). Runs from the **`neuro-caseboard-live` worktree** (see below). Health: engine/corpus/synth all true, provider=openrouter.
  - Stop: `kill 417228`. Restart (from `/home/michael/PROJECTS/neuro-caseboard-live`): `setsid env SYNTH_PROVIDER=openrouter OPENROUTER_MODEL=z-ai/glm-5.2 ANALYZE_MODEL=google/gemini-3.1-flash-lite NEURO_CASEBOARD_WEB_DIST=$PWD/web/dist nohup python3 -m uvicorn api.server:app --host 0.0.0.0 --port 8001 >/tmp/live.log 2>&1 </dev/null &`
- **Cloudflare tunnel**: cloudflared **PID 431341** → **https://teaches-closing-livestock-tear.trycloudflare.com**
  - Ephemeral: dies on reboot/sleep; each new spin-up = new URL. Stop: `pkill -x cloudflared`.
  - NOTE: this WSL2 box can't resolve new `*.trycloudflare.com` subdomains locally — test from a phone or with `curl --doh-url https://1.1.1.1/dns-query <url>`.

## Worktrees (important: one is load-bearing)
- `/home/michael/PROJECTS/neuro-caseboard` — main checkout, branch `eval/literature-rewrite-arm`.
- `/home/michael/PROJECTS/neuro-caseboard-live` [`live/master` @ `07fa48f`] — **the live server's code home; do not remove while the server runs.** `ff` it to origin/master + restart the server to pick up new merges.
- 5 pre-existing loop/session worktrees under `.claude/worktrees/` and `.project-loop/wt` — not from this session; leave alone (one, `loop/cd-self-hosted-deploy`, pins the last stale `gone` branch).

## Open items / decisions for next session
1. **PR #79** (`add-tunnel-script`, `scripts/tunnel.sh`) is still open & clean — the `caseboard-tunnel` skill expects that script (we ran `cloudflared` directly instead). Merge it if you want the skill's happy path.
2. **Container not built/run this session — Docker daemon was unreachable.** The compose is now glm-configured but unverified end-to-end. When Docker is up: `cd neuro-caseboard-live && docker compose build && docker compose up` (needs `OPENROUTER_API_KEY` + `GOOGLE_CLOUD_PROJECT` in a box `.env`; both already in repo `.env`). Switching the live deploy from bare-uvicorn → container is optional.
3. **Automated CD is dormant** by design: `CD_ENABLED` repo var unset + no `v*` tag → `cd.yml` is a green no-op, no GHCR image. Arm it only if you want true continuous deploy.
4. **2 stale doc *remote* branches** (`docs/groundedness-validation`, `docs/synth-default-runtime-note`) — content already on master; remote deletion was blocked by the safety classifier. Delete with `gh api -X DELETE repos/michaelandrewlongo-rgb/neuro-caseboard/git/refs/heads/<branch>` if wanted.
5. Live bare-uvicorn server goes **stale as master advances** — restart it (step above) to pick up merges.

## Gotchas discovered this session (save future debugging)
- **glm-5.2 is text-only on OpenRouter** (`input_modalities=['text']`) → figure images 404. Fixed (#85) but it's why synth drops images on glm. Vertex is multimodal.
- **Default↔deploy split**: `config.DEFAULTS` = glm/openrouter; the *container* (compose) now also = openrouter for Ask, but **Build/Case Explorer + operative briefing still need Vertex** (`CASEBOARD_LLM_PROVIDER=vertex`, `GOOGLE_CLOUD_PROJECT`, ADC). Keep both creds on the box.
- **Disambiguation (flash-lite) only fires when `ambiguity_gate` trips** — clear questions skip the LLM analyze call (the gate is a cheap non-LLM heuristic). Verified live: a clear query shows 2 glm calls (literature + woven), 0 flash.
- **Harness quirks on this box**: foreground `sleep` is blocked (use curl `--retry`/`timeout`); `pkill -f "<pattern in your own cmd>"` self-matches the shell — use `pkill -x <name>` or kill by PID.
- **Optional-dep test trap**: `openai`/`streamlit` etc. can't be imported at a test module's top level (required `.[dev]` CI omits them) — though `openai` is now core (#87), so that specific one is resolved.

## Where things live
- Architecture: `docs/NEURO_CASEBOARD_ARCHITECTURE.md`, `docs/NEURO_CASEBOARD_DIAGRAMS.md`, `docs/ask-pathway-llm-calls.{svg,png}` (untracked; offer to commit).
- Persistent memory (read at session start): `~/.claude/projects/-home-michael-PROJECTS-neuro-caseboard/memory/` — esp. `runtime-engine-config`, `glm-figure-image-incompat`, `model-bakeoff-knob-findings`.
- Project gotchas: `CLAUDE.md` (current & accurate on engine defaults).
