import hashlib
import hmac

from fastapi.responses import HTMLResponse

COOKIE_NAME = "neuro_auth"
# /sw.js is open so a logged-out browser can always fetch the service worker. The
# worker is now a kill-switch (no secrets); gating it would 303-redirect the SW
# update to /login, which is an invalid SW script, leaving a stale worker stuck.
OPEN_PATHS = {"/login", "/healthz", "/sw.js"}


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
