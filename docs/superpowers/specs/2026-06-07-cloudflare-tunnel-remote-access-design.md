# Cloudflare Tunnel + Passcode — Remote Access (toggleable)

**Date:** 2026-06-07
**Status:** Design approved; ready for implementation plan.
**Builds on:** Phase 2c (FastAPI `server/` + PWA `webapp/`, merged to `master`). The
server already exposes the app on `localhost:8000` over the unchanged `engine.query` seam.

## Motivation

Phase 2c's remote path (phone → Tailscale → Windows host → `netsh` portproxy → WSL2) is
fragile: it broke on a stopped Tailscale service, a stale WSL IP, and Windows firewall/admin
friction. Replace it with a **Cloudflare quick tunnel** run *from inside WSL2*, which dials
**outbound** to Cloudflare and needs **no inbound networking at all** (no portproxy, no
firewall rule, no Tailscale). The phone opens a normal `https://` URL. Because that URL is
public, add a lightweight **passcode** so only the user can use it. Everything is
**toggleable**: local mode (today's behavior) is unchanged; remote mode is opt-in.

## Decisions (locked during brainstorming)

- **Quick tunnel, not named.** `cloudflared tunnel --url http://localhost:8000` gives an
  instant `https://<random>.trycloudflare.com` with zero account/domain setup. (Rejected:
  named tunnel + Cloudflare Access — needs a domain the user doesn't have; documented as a
  future upgrade for a permanent URL.)
- **Passcode-cookie auth.** A public URL needs a gate. A correct passcode sets a signed,
  HttpOnly session cookie. (Rejected: HTTP Basic Auth — re-prompts awkwardly on iOS, no
  logout; Cloudflare Access — needs a domain.)
- **Engine + corpus stay local.** The tunnel only forwards to `localhost:8000`; retrieval,
  index, and copyrighted figures never leave the machine. Same data boundary as Phase 2c.
- **Toggle = one setting + an opt-in script.** `APP_PASSCODE` empty → open (local mode,
  unchanged). `APP_PASSCODE` set → required. `tunnel.sh` is the only new thing you run for
  remote access, and it **refuses to start unless a passcode is set** (no accidental naked
  exposure). The Tailscale bridge scripts remain as an alternate local-network option.
- **Engine code untouched.** All changes live in `server/`, `scripts/`, config, tests, docs.

## Architecture & data flow

```
  Phone (Safari)
        │  https://<random>.trycloudflare.com   (real TLS, public)
        ▼
  Cloudflare edge
        │  outbound tunnel (cloudflared dialed OUT from WSL2 — no inbound ports)
        ▼
  WSL2: cloudflared ──► http://localhost:8000 ──► FastAPI (server.main:app)
        │                                              │
        │  passcode middleware: no valid cookie ──► 303 /login (GET) or 401 (POST)
        ▼                                              ▼
  /login passcode screen ── correct ──► Set-Cookie (signed, HttpOnly) ──► app
                                                       │
                                                       ▼
                                          engine.query (unchanged, local, on-box)
```

Local mode is identical to today minus the tunnel: `serve.sh` only, `APP_PASSCODE` empty,
no auth, reach it over LAN/Tailscale.

## Components

```
server/
  auth.py        # NEW: cookie-token helpers, is_authed(), the /login page HTML
  main.py        # MODIFY: add passcode middleware + GET/POST /login; read CONFIG.app_passcode
scripts/
  tunnel.sh      # NEW: assert APP_PASSCODE set + server up, then run cloudflared --url localhost:8000
engine/config.py # MODIFY: add APP_PASSCODE (default "") to DEFAULTS + Config
requirements.txt # MODIFY: add python-multipart (form parsing for /login POST)
tests/
  test_auth.py   # NEW: open when unset; gated + login flow when set; /healthz open
README.md        # MODIFY: "Remote access (Cloudflare tunnel)" section
```

## Auth design (the one nuanced part)

- **Setting:** `APP_PASSCODE` (config, from `.env`/env). Empty string disables auth entirely.
- **Token:** `expected = sha256("neuro-rag:" + APP_PASSCODE)`. The session cookie
  `neuro_auth` holds that hex digest; the check is `hmac.compare_digest(cookie, expected)`
  (constant-time). The raw passcode is never stored in the cookie.
- **Middleware** (`@app.middleware("http")`, runs before routes AND the static mount, so it
  gates everything): if `APP_PASSCODE` is empty → pass through. Else allow the open
  allowlist `{/login, /healthz}`; if the cookie is valid → pass through; otherwise → `303`
  redirect to `/login` for HTML GET navigations, else `401`.
- **`/login`:** `GET` serves a **self-contained** passcode form (inline CSS — depends on no
  gated asset). `POST` (form field `passcode`) compares constant-time to `APP_PASSCODE`; on
  match, `303` redirect to `/` with `Set-Cookie neuro_auth=<expected>` —
  `HttpOnly`, `SameSite=Lax`, `Max-Age=30d`, and `Secure` when the request is https
  (detected via `X-Forwarded-Proto`, which cloudflared sets — so Secure is on through the
  tunnel but off for the http TestClient/local case so tests and local http still work).
- **Scope:** `/healthz` stays open (liveness/probe). `/ask`, `/figures`, the app shell, and
  static assets are all gated when a passcode is set.
- **Expired-session UX:** the PWA's `/ask` handler treats an HTTP `401` as "session
  expired" and redirects to `/login` (instead of showing the generic "can't reach server"
  error), so a stale cookie sends you cleanly back to the passcode screen.

## `tunnel.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Safety: never expose a naked server.
grep -qE '^APP_PASSCODE=.+' .env || { echo "Set APP_PASSCODE in .env before tunnelling."; exit 1; }
curl -sf -m 3 localhost:8000/healthz >/dev/null || { echo "Start the server first: ./scripts/serve.sh"; exit 1; }
echo "Opening a public Cloudflare tunnel to localhost:8000. Copy the https URL below to your phone."
exec cloudflared tunnel --url http://localhost:8000
```

`cloudflared` is a single binary; install is a documented one-liner (download to the repo or
`~/.local/bin`, or `apt`). No Cloudflare account/login is needed for a quick tunnel.

## Testing

- `tests/test_auth.py` (engine mocked, `TestClient`):
  - `APP_PASSCODE` unset → `/`, `/ask` reachable (no auth) — current behavior preserved.
  - `APP_PASSCODE` set, no cookie → `/` returns `303→/login`; `/ask` returns `401`;
    `/login` GET returns `200` with a passcode field; `/healthz` returns `200`.
  - `POST /login` with the right passcode → `303` + sets `neuro_auth` cookie; reusing that
    cookie → `/ask` returns `200`. Wrong passcode → `200` login page (no cookie).
- Existing `tests/test_server.py` stays green (those tests set no passcode → auth off).
- `tunnel.sh` validated manually (bash `-n`; the cloudflared run is the manual e2e).

## Out of scope (documented future)

- Named tunnel + Cloudflare Access for a **permanent** URL + SSO (needs a domain).
- Per-user accounts / multi-user (single shared passcode is enough here).
- Rate limiting / WAF (Cloudflare quick tunnels already absorb scanner noise; the passcode
  blocks access).

## Known trade-offs

- The quick-tunnel URL **changes each time `cloudflared` restarts** (stable while it runs).
  Re-copy it to the phone after a restart, or do the named-tunnel upgrade later.
- `cloudflared` must be running for remote access (alongside `serve.sh`); local mode needs
  neither.
