import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    return to_response(engine_query(req.question, CONFIG))


@app.get("/healthz")
def healthz():
    return {"warm": _state["warm"]}
