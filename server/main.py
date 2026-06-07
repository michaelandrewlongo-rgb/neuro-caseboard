import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine.config import load_config
from engine.query import get_engine, query as engine_query

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
