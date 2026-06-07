import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from engine.config import load_config
from engine.query import get_engine, query as engine_query

from .auth import COOKIE_NAME, OPEN_PATHS, expected_token, is_authed, login_page
from .schemas import AskRequest, AskResponse, to_response

CONFIG = load_config()
_state = {"warm": False}


@asynccontextmanager
async def lifespan(app):
    # Warm the heavy models once so the first real request isn't slow. Never let
    # a warm failure (e.g. missing GPU in a test env) prevent the app from serving.
    try:
        get_engine(CONFIG)
        _state["warm"] = True
    except Exception:
        logging.exception("Engine warm failed; serving cold")
        _state["warm"] = False
    yield


app = FastAPI(title="Neuro Textbook RAG", lifespan=lifespan)


@app.middleware("http")
async def passcode_gate(request: Request, call_next):
    pc = CONFIG.app_passcode
    if not pc or request.url.path in OPEN_PATHS or is_authed(request, pc):
        return await call_next(request)
    accept = request.headers.get("accept", "")
    if request.method == "GET" and ("text/html" in accept or "*/*" in accept):
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


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    return to_response(engine_query(req.question, CONFIG), CONFIG.assets_dir)


@app.get("/healthz")
def healthz():
    return {"warm": _state["warm"]}


@app.get("/figures/{name:path}")
def figure(name: str):
    # name includes the per-book subdir, e.g. "Rhoton Cranial Anatomy/p0001.png".
    assets = Path(CONFIG.assets_dir).resolve()
    path = (assets / name).resolve()  # resolve() so traversal/symlinks can't escape
    if not path.is_relative_to(assets) or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png")


# Static PWA at root — MUST be mounted last so /ask, /healthz, /figures win.
_WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
app.mount("/", StaticFiles(directory=_WEBAPP_DIR, html=True), name="webapp")
