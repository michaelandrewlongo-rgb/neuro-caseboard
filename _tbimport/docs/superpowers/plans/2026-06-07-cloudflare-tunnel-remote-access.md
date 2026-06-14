# Cloudflare Tunnel + Passcode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a toggleable remote-access path — a Cloudflare quick tunnel from WSL2 plus an optional passcode gate — so the phone reaches the app over a public `https://` URL with no inbound networking, while local mode stays unchanged.

**Architecture:** `cloudflared` dials outbound from WSL2 to Cloudflare and forwards to `localhost:8000`. A FastAPI middleware enforces a passcode (signed HttpOnly cookie) only when `APP_PASSCODE` is set; empty = open (today's local mode). `engine/` is untouched.

**Tech Stack:** FastAPI middleware + `Form`, `python-multipart`, `cloudflared` (single binary), pytest + `TestClient`.

**Spec:** `docs/superpowers/specs/2026-06-07-cloudflare-tunnel-remote-access-design.md`

**Existing facts:** `server/main.py` has `CONFIG = load_config()`, a lifespan, `/ask`, `/healthz`, `/figures/{name:path}`, and a `StaticFiles` mount at `/` (added LAST). Tests mock `server.main.get_engine` / `server.main.engine_query`. `engine/config.py` has a `DEFAULTS` dict + `Config` dataclass + `load_config()`.

## File structure

```
engine/config.py    # MODIFY: APP_PASSCODE default "" → Config.app_passcode
requirements.txt    # MODIFY: + python-multipart
server/auth.py      # NEW: cookie token + validity helpers + login page HTML
server/main.py      # MODIFY: passcode middleware + GET/POST /login
webapp/app.js       # MODIFY: on 401 from /ask, redirect to /login
webapp/sw.js        # MODIFY: bump cache v2 → v3
scripts/tunnel.sh   # NEW: guard + run cloudflared
tests/test_auth.py  # NEW: middleware + login flow
tests/test_server.py# MODIFY: pin app_passcode="" so existing tests ignore .env
README.md           # MODIFY: remote-access section
```

---

### Task 1: Config setting + dependency

**Files:** Modify `engine/config.py`, `requirements.txt`, `tests/test_config.py`

- [ ] **Step 1: Failing test** — append to `tests/test_config.py`:

```python
def test_default_app_passcode_is_empty(monkeypatch):
    monkeypatch.delenv("APP_PASSCODE", raising=False)
    cfg = load_config(env_file="does-not-exist.env")
    assert cfg.app_passcode == ""
```

- [ ] **Step 2: Run it, expect FAIL** — `python3 -m pytest tests/test_config.py::test_default_app_passcode_is_empty -v` → `AttributeError: 'Config' object has no attribute 'app_passcode'`.

- [ ] **Step 3: Implement.** In `engine/config.py`: add `"APP_PASSCODE": "",` to the `DEFAULTS` dict; add `app_passcode: str` to the `Config` dataclass; add `app_passcode=get("APP_PASSCODE"),` to the `Config(...)` construction in `load_config`.

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_config.py -v`.

- [ ] **Step 5: Add dep + install.** Append `python-multipart>=0.0.9` to `requirements.txt`; run `python3 -m pip install python-multipart`. Verify `python3 -c "import multipart"` (the import name is `multipart`).

- [ ] **Step 6: Commit**

```bash
git add engine/config.py requirements.txt tests/test_config.py
git commit -m "feat: add APP_PASSCODE config + python-multipart dep"
```

---

### Task 2: Auth helpers + login page (`server/auth.py`)

**Files:** Create `server/auth.py`, `tests/test_auth.py`

- [ ] **Step 1: Failing unit tests** — create `tests/test_auth.py`:

```python
from server.auth import expected_token, cookie_is_valid, login_page, COOKIE_NAME


def test_expected_token_is_deterministic_and_passcode_specific():
    assert expected_token("abc") == expected_token("abc")
    assert expected_token("abc") != expected_token("xyz")
    assert len(expected_token("abc")) == 64  # sha256 hex


def test_cookie_is_valid_logic():
    assert cookie_is_valid("anything", "") is True          # auth disabled
    assert cookie_is_valid("", "secret") is False           # no cookie
    assert cookie_is_valid("wrong", "secret") is False
    assert cookie_is_valid(expected_token("secret"), "secret") is True


def test_login_page_has_passcode_field():
    body = login_page().body.decode()
    assert 'name="passcode"' in body
    assert "neuro" in body.lower()
    assert "passcode" in login_page(error=True).body.decode().lower()
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_auth.py -v` → `ModuleNotFoundError: No module named 'server.auth'`.

- [ ] **Step 3: Implement** — create `server/auth.py`:

```python
import hashlib
import hmac

from fastapi.responses import HTMLResponse

COOKIE_NAME = "neuro_auth"
OPEN_PATHS = {"/login", "/healthz"}


def expected_token(passcode: str) -> str:
    """Stateless session token: the cookie holds this, never the raw passcode."""
    return hashlib.sha256(("neuro-rag:" + passcode).encode()).hexdigest()


def cookie_is_valid(cookie_value: str, passcode: str) -> bool:
    if not passcode:           # auth disabled (local mode)
        return True
    return hmac.compare_digest(cookie_value or "", expected_token(passcode))


def is_authed(request, passcode: str) -> bool:
    return cookie_is_valid(request.cookies.get(COOKIE_NAME, ""), passcode)


def login_page(error: bool = False) -> HTMLResponse:
    msg = '<p class="err">Wrong passcode — try again.</p>' if error else ""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light">
<title>Neuro RAG — sign in</title>
<style>
  body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
  .card{{background:#fff;border-radius:16px;padding:28px 24px;width:min(360px,86vw);
    box-shadow:0 12px 40px rgba(0,0,0,.35)}}
  h1{{font-size:17px;margin:0 0 4px;color:#0f172a}}
  p.sub{{margin:0 0 18px;color:#6b7280;font-size:13px}}
  p.err{{margin:0 0 14px;color:#b91c1c;font-size:13px}}
  input{{width:100%;box-sizing:border-box;border:1px solid #d6dae0;border-radius:12px;
    padding:13px 14px;font-size:16px;color:#0f172a;background:#fff;margin-bottom:12px}}
  button{{width:100%;border:none;background:#1d4ed8;color:#fff;border-radius:12px;
    padding:13px;font-size:15px;font-weight:600}}
</style></head>
<body>
  <form method="post" action="/login" class="card">
    <h1>Neuro Textbook RAG</h1>
    <p class="sub">Enter the passcode to continue.</p>
    {msg}
    <input type="password" name="passcode" placeholder="Passcode" autofocus
      autocomplete="current-password" inputmode="text">
    <button type="submit">Enter</button>
  </form>
</body></html>""")
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_auth.py -v`.

- [ ] **Step 5: Commit**

```bash
git add server/auth.py tests/test_auth.py
git commit -m "feat: passcode auth helpers + self-contained login page"
```

---

### Task 3: Passcode middleware + /login routes

**Files:** Modify `server/main.py`, `tests/test_auth.py` (append), `tests/test_server.py` (pin passcode off)

- [ ] **Step 1: Failing integration tests** — append to `tests/test_auth.py`:

```python
from engine.query import QueryResult


def _app(monkeypatch, passcode):
    import server.main as m
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    monkeypatch.setattr(m, "engine_query", lambda q, config=None: QueryResult(answer="ok"))
    monkeypatch.setattr(m.CONFIG, "app_passcode", passcode)
    return TestClient(m.app)


def test_open_when_no_passcode(monkeypatch):
    with _app(monkeypatch, "") as c:
        assert c.get("/healthz").status_code == 200
        assert c.post("/ask", json={"question": "x"}).status_code == 200


def test_gated_without_cookie(monkeypatch):
    with _app(monkeypatch, "letmein") as c:
        nav = c.get("/", follow_redirects=False)
        assert nav.status_code == 303 and nav.headers["location"] == "/login"
        assert c.post("/ask", json={"question": "x"}).status_code == 401
        assert c.get("/login").status_code == 200
        assert c.get("/healthz").status_code == 200   # liveness stays open


def test_login_flow_grants_access(monkeypatch):
    with _app(monkeypatch, "letmein") as c:
        bad = c.post("/login", data={"passcode": "nope"}, follow_redirects=False)
        assert bad.status_code == 200                  # login page re-shown
        assert COOKIE_NAME not in bad.cookies
        good = c.post("/login", data={"passcode": "letmein"}, follow_redirects=False)
        assert good.status_code == 303
        assert good.cookies.get(COOKIE_NAME)           # cookie set
        # TestClient keeps the cookie; gated route now works
        assert c.post("/ask", json={"question": "x"}).status_code == 200
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_auth.py -k "gated or login_flow or open_when" -v` (middleware not present → `/` returns 200 not 303, `/ask` 200 not 401).

- [ ] **Step 3: Implement in `server/main.py`.** Extend the imports and add the middleware + routes.

Change the FastAPI import line and add `Request`, `Form`, response + auth imports near the top (after the existing imports):

```python
import hmac
from fastapi import FastAPI, HTTPException, Form, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from .auth import COOKIE_NAME, OPEN_PATHS, expected_token, is_authed, login_page
```

Add this middleware and the two routes **after** `app = FastAPI(...)` and before the `/figures` route (anywhere among the routes is fine; the static mount must remain last):

```python
@app.middleware("http")
async def passcode_gate(request: Request, call_next):
    pc = CONFIG.app_passcode
    if not pc or request.url.path in OPEN_PATHS or is_authed(request, pc):
        return await call_next(request)
    if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login", status_code=303)
    return Response("Unauthorized", status_code=401)


@app.get("/login")
def login_get():
    return login_page()


@app.post("/login")
def login_post(request: Request, passcode: str = Form("")):
    pc = CONFIG.app_passcode
    if pc and hmac.compare_digest(passcode, pc):
        resp = RedirectResponse("/", status_code=303)
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        resp.set_cookie(COOKIE_NAME, expected_token(pc), max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite="lax", secure=secure)
        return resp
    return login_page(error=True)
```

- [ ] **Step 4: Keep existing server tests deterministic.** In `tests/test_server.py`, pin the passcode off wherever a `TestClient` is built (so a real `APP_PASSCODE` in `.env` can't gate them). Add `monkeypatch.setattr(m.CONFIG, "app_passcode", "")` immediately after the `monkeypatch.setattr(m, "get_engine", ...)` line in: the `_client` helper, `test_figures_served_and_guarded`, `test_figures_rejects_symlink_escape`, and `test_pwa_shell_and_assets_served`. (`test_healthz_cold` only hits `/healthz`, which is always open, so it needs no change.)

- [ ] **Step 5: Run, expect PASS** — `python3 -m pytest tests/test_auth.py tests/test_server.py -v` (all pass).

- [ ] **Step 6: Commit**

```bash
git add server/main.py tests/test_auth.py tests/test_server.py
git commit -m "feat: passcode middleware + /login; keep existing tests passcode-off"
```

---

### Task 4: PWA handles 401 (expired session) + cache bump

**Files:** Modify `webapp/app.js`, `webapp/sw.js`

- [ ] **Step 1: Edit `webapp/app.js`.** In the `ask()` function, the fetch currently does `if(!r.ok) throw new Error("HTTP " + r.status);`. Replace that line with a 401 redirect first:

```javascript
    if(r.status === 401){ window.location.href = "/login"; return; }
    if(!r.ok) throw new Error("HTTP " + r.status);
```

- [ ] **Step 2: Bump the service-worker cache.** In `webapp/sw.js`, change `const CACHE = "neuro-rag-v2";` to `const CACHE = "neuro-rag-v3";` (so installed phones pull the updated `app.js`).

- [ ] **Step 3: Sanity check.** Run `node --check webapp/app.js` (expect "no output" = OK; skip if node absent). Run `python3 -m pytest tests/test_server.py::test_pwa_shell_and_assets_served -v` (still 200s).

- [ ] **Step 4: Commit**

```bash
git add webapp/app.js webapp/sw.js
git commit -m "feat: PWA redirects to /login on 401; bump SW cache v3"
```

---

### Task 5: `tunnel.sh` launcher

**Files:** Create `scripts/tunnel.sh`

- [ ] **Step 1: Create `scripts/tunnel.sh`:**

```bash
#!/usr/bin/env bash
# Expose the local server publicly via a Cloudflare quick tunnel. Run AFTER
# ./scripts/serve.sh, from the repo root inside WSL2. Requires cloudflared.
set -euo pipefail
cd "$(dirname "$0")/.."

# Safety: never expose a naked (passcode-less) server to the public internet.
if ! grep -qE '^APP_PASSCODE=.+' .env 2>/dev/null; then
  echo "Refusing to tunnel: set APP_PASSCODE=<something> in .env first (the URL is public)."
  exit 1
fi
if ! curl -sf -m 3 localhost:8000/healthz >/dev/null; then
  echo "Server not responding on :8000 — start it first:  ./scripts/serve.sh"
  exit 1
fi
if ! command -v cloudflared >/dev/null; then
  echo "cloudflared not installed. One-time install:"
  echo '  mkdir -p ~/.local/bin && curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared'
  echo '  (ensure ~/.local/bin is on PATH)'
  exit 1
fi

echo "Opening a public Cloudflare tunnel to localhost:8000."
echo "Copy the https://<...>.trycloudflare.com URL printed below onto your phone."
exec cloudflared tunnel --url http://localhost:8000
```

- [ ] **Step 2: Make executable + syntax-check.** `chmod +x scripts/tunnel.sh && bash -n scripts/tunnel.sh` (expect no output).

- [ ] **Step 3: Commit**

```bash
git add scripts/tunnel.sh
git commit -m "feat: tunnel.sh — guarded cloudflared quick tunnel launcher"
```

---

### Task 6: Docs + full-suite verification

**Files:** Modify `README.md`

- [ ] **Step 1: Full suite green** — `python3 -m pytest -q` (expect all pass; the prior suite + `test_auth.py`).

- [ ] **Step 2: README — add a "Remote access (Cloudflare tunnel)" subsection** under the existing "Phase 2c — phone/web app" section:

```markdown
### Remote access (Cloudflare tunnel)

To reach the app from anywhere without the Tailscale/WSL bridge:

1. One-time: install `cloudflared` in WSL2 —
   `mkdir -p ~/.local/bin && curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared`
2. Set a passcode in `.env`: `APP_PASSCODE=<something only you know>` (the public URL needs a gate).
3. `./scripts/serve.sh` in one WSL terminal, then `./scripts/tunnel.sh` in another.
4. Open the printed `https://<...>.trycloudflare.com` on your phone, enter the passcode, done.

Local mode is unchanged: leave `APP_PASSCODE` empty and just run `serve.sh` (reach it over
LAN/Tailscale). The quick-tunnel URL changes each time `cloudflared` restarts.
```

Also append to the "Design docs" list:
```markdown
- Tunnel spec: `docs/superpowers/specs/2026-06-07-cloudflare-tunnel-remote-access-design.md`
- Tunnel plan: `docs/superpowers/plans/2026-06-07-cloudflare-tunnel-remote-access.md`
```

- [ ] **Step 3: Manual e2e (human-gated).** Set `APP_PASSCODE` in `.env`, `serve.sh`, `tunnel.sh`, open the URL on the phone, confirm: login page renders (light), wrong passcode rejected, right passcode → app loads + a query works, figures load. Reload after entering — stays logged in (cookie).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: remote access via Cloudflare tunnel"
```

---

## Self-review (done during planning)

- **Spec coverage:** tunnel via `tunnel.sh` (Task 5) · `APP_PASSCODE` toggle (Task 1) · cookie-token auth + middleware + `/login` (Tasks 2–3) · `/healthz` open, `/ask`+`/figures` gated (Task 3) · Secure-via-`X-Forwarded-Proto` (Task 3) · 401→/login PWA UX (Task 4) · tests open-when-unset / gated / login-flow (Tasks 2–3) · existing tests kept green (Task 3 Step 4) · docs (Task 6). No spec item unmapped.
- **No placeholders:** every step has concrete code/commands.
- **Type/name consistency:** `APP_PASSCODE`/`app_passcode`, `COOKIE_NAME="neuro_auth"`, `expected_token`/`cookie_is_valid`/`is_authed`/`login_page`, `OPEN_PATHS` used identically across tasks. `python-multipart` import name is `multipart`. Engine seam (`engine_query`, `get_engine`, `QueryResult`) matches existing usage.
