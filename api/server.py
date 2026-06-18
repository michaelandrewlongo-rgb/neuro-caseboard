"""FastAPI wrapper over the existing neuro-caseboard engine.

Local-first, no auth: anyone who can reach localhost:8000 gets in (the loop spec forbids
any APP_PASSCODE/login gate on this surface). The engine stays authoritative — every
endpoint imports and forwards to the SAME functions the CLI (`neuro_caseboard.cli`) and the
Streamlit app (`app/streamlit_app.py`) call. Nothing about retrieval/RAG/PubMed is
reimplemented here.

Honest degradation: /api/health reports what is and isn't available (Vertex synthesis,
textbook index, cards bank, NCBI key) by probing the engine's real config. The POST lanes
(added in later milestones) forward the engine's real result OR its real error — never a
fabricated dossier/citation/card.

Run (from the repo root): uvicorn api.server:app --port 8000 --reload
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="neuro-caseboard API", version="0.1.0")

# The browser talks to the API through the Vite dev-proxy (same origin), so CORS is not
# strictly required. We still allow the local Vite origins so hitting the API directly from
# the dev server (or a curl from the browser devtools) doesn't trip a CORS wall in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _adc_present() -> bool:
    """True if Application Default Credentials are resolvable for Vertex (file or env)."""
    explicit = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if explicit and Path(explicit).is_file():
        return True
    default = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return default.is_file()


def _probe_engine() -> dict:
    """Best-effort import of the engine entry points. Never raises — the site must boot
    even if the engine import is broken, and say so honestly."""
    try:
        import neuro_caseboard.cli  # noqa: F401  (exercises cli -> pipeline -> retrieve -> neuro_core)
        return {"ok": True, "error": None}
    except Exception as e:  # pragma: no cover - exercised only when the env is broken
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _probe_synth() -> dict:
    """Synthesis lane (Ask/Build LLM). This deployment uses Vertex (Gemini), NOT Anthropic:
    available iff provider==vertex, a GCP project is configured, ADC is resolvable, and the
    google-genai client import succeeds."""
    info = {"available": False, "provider": None, "project": None,
            "adc": False, "client_import": False, "detail": None}
    try:
        from neuro_core.config import load_config
        cfg = load_config()
        info["provider"] = cfg.synth_provider
        info["project"] = cfg.google_cloud_project or None
        info["adc"] = _adc_present()
        try:
            import google.genai  # noqa: F401
            info["client_import"] = True
        except Exception as e:
            info["detail"] = f"google-genai not importable: {type(e).__name__}: {e}"
        if cfg.synth_provider == "vertex":
            info["available"] = bool(info["project"]) and info["adc"] and info["client_import"]
            if not info["available"] and info["detail"] is None:
                missing = []
                if not info["project"]:
                    missing.append("GOOGLE_CLOUD_PROJECT")
                if not info["adc"]:
                    missing.append("ADC credentials")
                info["detail"] = "missing: " + ", ".join(missing) if missing else None
        else:
            # Non-vertex providers (e.g. anthropic/openrouter) are out of scope for this
            # deployment; report provider but treat availability conservatively.
            info["detail"] = f"provider '{cfg.synth_provider}' not probed (deployment uses vertex)"
    except Exception as e:
        info["detail"] = f"{type(e).__name__}: {e}"
    return info


def _probe_corpus() -> dict:
    """Textbook retrieval availability: the LanceDB index dir must exist on disk. (CORPUS_DIR
    — the raw PDFs — is only needed to RE-index, not to query, so it does not gate corpus.)"""
    info = {"available": False, "index_dir": None, "corpus_dir": None, "detail": None}
    try:
        from neuro_core.config import load_config
        cfg = load_config()
        info["index_dir"] = str(cfg.index_dir)
        info["corpus_dir"] = str(cfg.corpus_dir)
        info["available"] = Path(cfg.index_dir).exists()
        if not info["available"]:
            info["detail"] = "textbook index not built at INDEX_DIR"
    except Exception as e:
        info["detail"] = f"{type(e).__name__}: {e}"
    return info


def _probe_cards() -> dict:
    """Board-review cards lane. The QUERYABLE `cards` table lives INSIDE the textbook INDEX_DIR
    (LanceDB stores it as `cards.lance/`); CARDS_SOURCE_DB is only the source deck used to BUILD
    it. So availability keys off the built table, not the source deck."""
    info = {"available": False, "table": None, "source_db": None, "detail": None}
    try:
        from neuro_core.config import load_config
        cfg = load_config()
        table = Path(cfg.index_dir) / "cards.lance"
        info["table"] = str(table)
        info["source_db"] = str(cfg.cards_source_db)
        info["available"] = table.exists()
        if not info["available"]:
            info["detail"] = "cards table not built in INDEX_DIR (run build_cards_index)"
    except Exception as e:
        info["detail"] = f"{type(e).__name__}: {e}"
    return info


def _probe_literature() -> dict:
    """Contemporary-literature (PubMed) lane. Enabled by config; an NCBI key is optional but
    recommended (keyless access is heavily rate-limited)."""
    info = {"enabled": False, "ncbi_key": False, "detail": None}
    try:
        from neuro_caseboard.literature.config import load_literature_config
        lc = load_literature_config()
        info["enabled"] = bool(lc.enabled)
        info["ncbi_key"] = bool(getattr(lc, "ncbi_api_key", ""))
        if info["enabled"] and not info["ncbi_key"]:
            info["detail"] = "no NCBI_API_KEY (keyless PubMed is rate-limited)"
    except Exception as e:
        info["detail"] = f"{type(e).__name__}: {e}"
    return info


@app.get("/api/health")
def health() -> dict:
    """Real availability snapshot the frontend uses to show what is / isn't working.

    Top-level booleans answer the loop spec's required shape; nested objects carry the
    detail (paths, missing pieces) for an honest, debuggable status panel.
    """
    engine = _probe_engine()
    synth = _probe_synth()
    corpus = _probe_corpus()
    cards = _probe_cards()
    literature = _probe_literature()
    return {
        # Required top-level shape (loop spec). anthropic_key is intentionally absent:
        # this deployment synthesizes via Vertex, so `synth` is the meaningful signal.
        "engine": engine["ok"],
        "synth": synth["available"],
        "corpus": corpus["available"],
        "cards_index": cards["available"],
        "ncbi_key": literature["ncbi_key"],
        # Detail for the status panel / debugging.
        "detail": {
            "engine": engine,
            "synth": synth,
            "corpus": corpus,
            "cards": cards,
            "literature": literature,
        },
    }


# ---------------------------------------------------------------------------------------------
# Image serving: figures come back from the engine as ABSOLUTE local filesystem paths (under the
# configured assets dir). A browser can't read those, so the frontend references them via
# /api/figure?path=<abs>, and we serve ONLY files that resolve inside a whitelisted root — no
# arbitrary file read.
# ---------------------------------------------------------------------------------------------

def _image_roots() -> list[Path]:
    """Whitelisted roots for /api/figure. The engine keeps both textbook plates (assets/figures)
    and card media (assets/cards) under one assets tree, so we allow that tree's root — bounded
    to the engine's image assets, never the whole filesystem."""
    roots: list[Path] = []
    try:
        from neuro_core.config import load_config
        cfg = load_config()
        candidates = [
            cfg.assets_dir,
            cfg.assets_dir.parent,  # the `assets/` root → covers figures/ AND cards/
            Path(cfg.cards_media_dir) if cfg.cards_media_dir else None,
        ]
        for p in candidates:
            if p:
                try:
                    roots.append(Path(p).resolve())
                except Exception:
                    pass
    except Exception:
        pass
    return roots


def _safe_image_path(path: str) -> Path | None:
    """Resolve *path* and return it only if it is a real file inside a whitelisted root."""
    if not path:
        return None
    try:
        p = Path(path).resolve()
    except Exception:
        return None
    if not p.is_file():
        return None
    for root in _image_roots():
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    return None


def _image_url(image_path: str | None) -> str | None:
    if not image_path:
        return None
    return f"/api/figure?path={quote(image_path, safe='')}"


@app.get("/api/figure")
def figure(path: str):
    """Serve a whitelisted figure/plate image by absolute path (referenced by /api/ask etc.)."""
    p = _safe_image_path(path)
    if p is None:
        return JSONResponse(status_code=404, content={"error": "image not found or not allowed"})
    return FileResponse(p)


# ---------------------------------------------------------------------------------------------
# Ask: forward neuro_caseboard.qa.answer_question (the SAME call the CLI/Streamlit use). Returns
# a cited answer + figures + the contemporary-literature block, OR a clarification when the
# question is ambiguous, OR an honest error/unavailable state — never a fabricated answer.
# ---------------------------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    # Local single-user tool: default to bypassing the GPU-readiness guard so it "just runs".
    # A real GpuNotReadyError (e.g. genuinely out of memory) is still surfaced honestly.
    force: bool = True


def _citation_location(book: str, chapter: str, page) -> str:
    loc = book or ""
    if chapter:
        loc += f", {chapter}"
    if page is not None:
        loc += f", p.{page}"
    return loc


def _citation_dict(c) -> dict:
    book = getattr(c, "book", "")
    chapter = getattr(c, "chapter", "") or ""
    page = getattr(c, "page", None)
    return {
        "n": getattr(c, "n", None),
        "book": book,
        "chapter": chapter,
        "page": page,
        "location": _citation_location(book, chapter, page),
    }


def _figure_dict(f) -> dict:
    book = getattr(f, "book", "")
    chapter = getattr(f, "chapter", "") or ""
    page = getattr(f, "page", None)
    image_path = getattr(f, "image_path", "") or ""
    return {
        "source_n": getattr(f, "source_n", None),
        "book": book,
        "chapter": chapter,
        "page": page,
        "caption": getattr(f, "caption", "") or "",
        "location": _citation_location(book, chapter, page),
        "image_url": _image_url(image_path),
        "image_available": _safe_image_path(image_path) is not None,
    }


def _literature_dict(lit) -> dict | None:
    if lit is None or not getattr(lit, "narrative", ""):
        return None
    cites = []
    for c in getattr(lit, "citations", []) or []:
        doi = getattr(c, "doi", "") or ""
        url = getattr(c, "url", "") or ""
        cites.append({
            "n": getattr(c, "n", None),
            "pmid": getattr(c, "pmid", ""),
            "title": getattr(c, "title", ""),
            "journal": getattr(c, "journal", ""),
            "year": getattr(c, "year", None),
            "doi": doi,
            "url": url,
            "link": f"https://doi.org/{doi}" if doi else url,
        })
    return {"narrative": lit.narrative, "citations": cites}


@app.post("/api/ask")
def ask(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty question"})

    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import Clarification
    from neuro_caseboard.qa import answer_question

    try:
        result = answer_question(question, force=req.force)
    except GpuNotReadyError as e:
        # Honest "try again" state — the retrieval models need GPU headroom right now.
        return JSONResponse(status_code=503,
                            content={"kind": "unavailable", "reason": f"GPU not ready: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"kind": "error", "error": f"{type(e).__name__}: {e}"})

    if isinstance(result, Clarification):
        return {
            "kind": "clarification",
            "question": getattr(result, "question", question),
            "variants": [
                {"label": getattr(v, "label", ""), "rewrite": getattr(v, "rewrite", "")}
                for v in getattr(result, "variants", [])
            ],
        }

    return {
        "kind": "answer",
        "answer": result.answer,
        "citations": [_citation_dict(c) for c in (result.citations or [])],
        "figures": [_figure_dict(f) for f in (result.figures or [])],
        "literature": _literature_dict(getattr(result, "literature", None)),
    }


# ---------------------------------------------------------------------------------------------
# Build: forward pipeline.build_dossier (the SAME call the CLI `build` / Streamlit "Build board"
# use) and serialize the full structured Dossier — sections -> claims (with Why: + checkbox
# sub-items + claim<->figure links) -> figures -> appendix -> evidence summary. Optional PDF via
# render_case_pdf. Never fabricates a section/claim/figure.
# ---------------------------------------------------------------------------------------------

# Small in-memory cache so the PDF export can reuse a just-built dossier instead of paying the
# (minutes-long) build cost twice. Single-user local tool; last few builds is plenty.
_DOSSIER_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_DOSSIER_CACHE_MAX = 8


def _build_key(topic: str, enrich: bool, use_llm: bool) -> str:
    return hashlib.sha1(f"{topic}|{enrich}|{use_llm}".encode()).hexdigest()[:16]


def _cache_dossier(topic: str, enrich: bool, use_llm: bool, dossier) -> str:
    key = _build_key(topic, enrich, use_llm)
    _DOSSIER_CACHE[key] = (topic, dossier)
    _DOSSIER_CACHE.move_to_end(key)
    while len(_DOSSIER_CACHE) > _DOSSIER_CACHE_MAX:
        _DOSSIER_CACHE.popitem(last=False)
    return key


def _claim_dict(c) -> dict:
    return {
        "text": getattr(c, "text", ""),
        "why": getattr(c, "why", "") or "",
        "status": getattr(c, "status", "supported"),
        "sub_items": list(getattr(c, "sub_items", []) or []),
        "figure_ids": list(getattr(c, "figure_ids", []) or []),
    }


def _figitem_dict(fi) -> dict:
    image_path = getattr(fi, "image_path", "") or ""
    return {
        "fig_id": getattr(fi, "fig_id", ""),
        "caption": getattr(fi, "caption", "") or "",
        "citation": getattr(fi, "citation", "") or "",
        "relevance": getattr(fi, "relevance", "") or "",
        "claim_ref": getattr(fi, "claim_ref", "") or "",
        "image_url": _image_url(image_path),
        "image_available": _safe_image_path(image_path) is not None,
    }


def _section_dict(s) -> dict:
    return {
        "heading": getattr(s, "heading", ""),
        "intro": getattr(s, "intro", "") or "",
        "claims": [_claim_dict(c) for c in getattr(s, "claims", []) or []],
        "figures": [_figitem_dict(f) for f in getattr(s, "figures", []) or []],
        "cross_refs": list(getattr(s, "cross_refs", []) or []),
    }


def _appendix_dict(ap) -> dict:
    entries = []
    for e in getattr(ap, "entries", []) or []:
        entries.append({
            "heading": getattr(e, "heading", ""),
            "items": list(getattr(e, "items", []) or []),
            "sources": list(getattr(e, "sources", []) or []),
        })
    return {"entries": entries}


def _dossier_dict(d) -> dict:
    s = d.summary
    return {
        "title": d.title,
        "summary": {
            "supported": getattr(s, "supported", 0),
            "to_verify": getattr(s, "to_verify", 0),
            "quarantined": getattr(s, "quarantined", 0),
        },
        "sections": [_section_dict(sec) for sec in d.sections],
        "appendix": _appendix_dict(d.appendix),
    }


class BuildRequest(BaseModel):
    topic: str
    enrich: bool = True
    use_llm: bool = True


def _do_build(topic: str, enrich: bool, use_llm: bool):
    from neuro_caseboard.pipeline import build_dossier
    return build_dossier(topic, enrich=enrich, use_llm=None if use_llm else False)


@app.post("/api/build")
def build(req: BuildRequest):
    topic = (req.topic or "").strip()
    if not topic:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty topic"})

    from neuro_core.gpu_guard import GpuNotReadyError
    try:
        dossier = _do_build(topic, req.enrich, req.use_llm)
    except GpuNotReadyError as e:
        return JSONResponse(status_code=503,
                            content={"kind": "unavailable", "reason": f"GPU not ready: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"kind": "error", "error": f"{type(e).__name__}: {e}"})

    build_id = _cache_dossier(topic, req.enrich, req.use_llm, dossier)
    return {
        "kind": "dossier",
        "build_id": build_id,
        "topic": topic,
        "dossier": _dossier_dict(dossier),
    }


class BuildPdfRequest(BaseModel):
    build_id: str | None = None
    topic: str | None = None
    enrich: bool = True
    use_llm: bool = True


@app.post("/api/build/pdf")
def build_pdf(req: BuildPdfRequest):
    # Reuse the cached dossier when we have its build_id; otherwise (re)build from the topic.
    topic = (req.topic or "").strip()
    dossier = None
    if req.build_id and req.build_id in _DOSSIER_CACHE:
        topic, dossier = _DOSSIER_CACHE[req.build_id]
    if dossier is None:
        if not topic:
            return JSONResponse(status_code=422,
                                content={"error": "need a cached build_id or a topic"})
        from neuro_core.gpu_guard import GpuNotReadyError
        try:
            dossier = _do_build(topic, req.enrich, req.use_llm)
            _cache_dossier(topic, req.enrich, req.use_llm, dossier)
        except GpuNotReadyError as e:
            return JSONResponse(status_code=503, content={"error": f"GPU not ready: {e}"})
        except Exception as e:
            return JSONResponse(status_code=500,
                                content={"error": f"{type(e).__name__}: {e}"})

    from neuro_caseboard.pipeline import render_case_pdf, _slug
    tmp_dir = Path(tempfile.mkdtemp(prefix="caseboard_pdf_"))
    pdf_path = tmp_dir / "case-board.pdf"
    try:
        render_case_pdf(dossier, topic, pdf_path)
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"error": f"PDF render failed: {type(e).__name__}: {e}"})
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=f"{_slug(topic)}-caseboard.pdf")


# ---------------------------------------------------------------------------------------------
# Cards: forward neuro_core.cards_query (the SAME call the CLI `cards` / Streamlit Cards lane use).
# Isolated lane — a question bank surfaces real matched cards, NO LLM synthesis. Honest states:
# `not_built` (cards table absent) is a first-class outcome, never faked.
# ---------------------------------------------------------------------------------------------

def _card_dict(c) -> dict:
    from neuro_core.cards_query import flagged_tags
    seen: set[str] = set()
    images = []
    for p in getattr(c, "image_paths", []) or []:
        if not p or p in seen:
            continue
        seen.add(p)
        images.append({"image_url": _image_url(p), "image_available": _safe_image_path(p) is not None})
    tags = getattr(c, "tags", "") or ""
    return {
        "id": getattr(c, "id", ""),
        "deck": getattr(c, "deck_name", "") or getattr(c, "deck_full", "") or "cards",
        "tags": tags,
        "flagged": flagged_tags(tags),
        "question_text": getattr(c, "question_text", "") or "",
        "answer_text": getattr(c, "answer_text", "") or "",
        "images": images,
    }


class CardsRequest(BaseModel):
    question: str
    k: int = 6


@app.post("/api/cards")
def cards(req: CardsRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty question"})

    from neuro_core.cards_query import cards_query, CardsIndexNotBuilt
    from neuro_core.gpu_guard import GpuNotReadyError
    try:
        res = cards_query(question, k=req.k)
    except CardsIndexNotBuilt as e:
        # First-class honest state: the deck simply hasn't been built into the index.
        return JSONResponse(status_code=200, content={"kind": "not_built", "reason": str(e)})
    except GpuNotReadyError as e:
        return JSONResponse(status_code=503,
                            content={"kind": "unavailable", "reason": f"GPU not ready: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"kind": "error", "error": f"{type(e).__name__}: {e}"})

    return {
        "kind": "cards",
        "query": getattr(res, "query", question),
        "cards": [_card_dict(c) for c in (res.cards or [])],
    }


@app.get("/api/ping")
def ping() -> dict:
    """Liveness check that touches nothing — proves the server itself is up."""
    return {"ok": True}
