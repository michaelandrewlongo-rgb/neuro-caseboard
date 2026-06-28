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

Serving the web UI: this app also serves the built React/Vite console (web/dist) at "/", so a
single process is the whole product — the redesigned GUI at "/", the engine at "/api/*". Build
the SPA first, then run the server:

    npm --prefix web run build          # produces web/dist (the redesigned console)
    uvicorn api.server:app --port 8001  # → GUI at http://127.0.0.1:8001/

If web/dist is absent, "/" returns an honest 503 ("web UI not built …") and the API still works.
For development use `npm run dev` instead (Vite hot-reload on :5173 proxying /api here). The dist
location can be overridden with NEURO_CASEBOARD_WEB_DIST.

Run (from the repo root): uvicorn api.server:app --port 8001 --reload
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

from neuro_caseboard.answer_verify import verification_to_dict

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
    """Synthesis lane (Ask/Build LLM). Probes the *configured* provider:
    - vertex: GCP project + ADC resolvable + google-genai import.
    - openrouter: OPENROUTER_API_KEY set + openai client import.
    - local: base URL set + openai client import.
    The probe is config-level (creds + client import), not a live API call."""
    info = {"available": False, "provider": None, "project": None,
            "adc": False, "client_import": False, "detail": None}
    try:
        from neuro_core.config import load_config
        cfg = load_config()
        info["provider"] = cfg.synth_provider
        info["project"] = cfg.google_cloud_project or None
        info["adc"] = _adc_present()
        if cfg.synth_provider == "vertex":
            try:
                import google.genai  # noqa: F401
                info["client_import"] = True
            except Exception as e:
                info["detail"] = f"google-genai not importable: {type(e).__name__}: {e}"
            info["available"] = bool(info["project"]) and info["adc"] and info["client_import"]
            if not info["available"] and info["detail"] is None:
                missing = []
                if not info["project"]:
                    missing.append("GOOGLE_CLOUD_PROJECT")
                if not info["adc"]:
                    missing.append("ADC credentials")
                info["detail"] = "missing: " + ", ".join(missing) if missing else None
        elif cfg.synth_provider in ("openrouter", "local"):
            try:
                import openai  # noqa: F401
                info["client_import"] = True
            except Exception as e:
                info["detail"] = f"openai not importable: {type(e).__name__}: {e}"
            if cfg.synth_provider == "openrouter":
                cred_ok = bool(getattr(cfg, "openrouter_api_key", "") or "")
                cred_name = "OPENROUTER_API_KEY"
            else:
                cred_ok = bool(getattr(cfg, "local_base_url", "") or "")
                cred_name = "LOCAL_BASE_URL"
            info["available"] = cred_ok and info["client_import"]
            if not info["available"] and info["detail"] is None and not cred_ok:
                info["detail"] = f"missing: {cred_name}"
        else:
            info["detail"] = f"unknown synth provider '{cfg.synth_provider}'"
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
        # Required top-level shape (loop spec). A first-party LLM-vendor key field is
        # intentionally absent: this deployment synthesizes via Vertex, so `synth` is the
        # meaningful signal.
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
    """Resolve *path* and return it only if it is a real file inside a whitelisted root. Tries the
    literal path first, then re-rooted fallbacks (shared with the engine read via
    neuro_core.asset_paths) for an index built at a different assets location."""
    if not path:
        return None
    from neuro_core.asset_paths import reroot_candidates
    roots = _image_roots()
    for cand in (Path(path), *reroot_candidates(path, roots)):
        try:
            cand = cand.resolve()  # collapse `..` BEFORE the whitelist check (no traversal escape)
        except Exception:
            continue
        if not cand.is_file():
            continue
        for root in roots:
            try:
                cand.relative_to(root)
                return cand
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
    # Set by the SPA on a variant-pick re-entry: the question is already a disambiguated
    # variant rewrite (unambiguous by construction), so skip the gate + analyze pass.
    skip_disambiguation: bool = False


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
    # Drop only when there is neither a narrative NOR any citations. The woven path
    # (LITERATURE_WEAVE) sets narrative="" because the prose IS the answer, but still
    # carries [L#] citations — surface them so the inline [L#] markers aren't dangling.
    if lit is None or (not getattr(lit, "narrative", "") and not getattr(lit, "citations", None)):
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
        result = answer_question(question, force=req.force,
                                 skip_disambiguation=req.skip_disambiguation)
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
        "verification": verification_to_dict(getattr(result, "verification", None)),
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
    use_prefs: bool = True


def _do_build(topic: str, enrich: bool, use_llm: bool, prefs=None):
    from neuro_caseboard.pipeline import build_dossier
    return build_dossier(topic, enrich=enrich, use_llm=None if use_llm else False, prefs=prefs)


@app.post("/api/build")
def build(req: BuildRequest):
    topic = (req.topic or "").strip()
    if not topic:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty topic"})

    from neuro_core.gpu_guard import GpuNotReadyError
    prefs = None
    if req.use_prefs:
        from neuro_caseboard.preferences import load_preferences, default_store_path
        prefs = load_preferences(default_store_path()) or None
    try:
        dossier = _do_build(topic, req.enrich, req.use_llm, prefs)
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
# Briefing: the Operative Briefing Bundle surface (spec §9). Additive to /api/build*. Builds the
# bundle (pipeline.build_briefing_bundle — the SAME call the renderer/CLI verification use),
# caches the REAL bundle object, and serves it as JSON with figures augmented for the browser.
# The PDF endpoint serves the CACHED bundle (exported == displayed) — never a silent rebuild.
# ---------------------------------------------------------------------------------------------

from neuro_caseboard.briefing_model import BRIEFING_SCHEMA_VERSION

_BRIEFING_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_BRIEFING_CACHE_MAX = 8


def _briefing_key(topic: str, enrich: bool, use_llm: bool, use_prefs: bool) -> str:
    # schema_version in the key so a model bump can't collide with a stale cached bundle.
    raw = f"{BRIEFING_SCHEMA_VERSION}|{topic}|{enrich}|{use_llm}|{use_prefs}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _cache_briefing(topic: str, enrich: bool, use_llm: bool, use_prefs: bool, bundle) -> str:
    key = _briefing_key(topic, enrich, use_llm, use_prefs)
    _BRIEFING_CACHE[key] = (topic, bundle)
    _BRIEFING_CACHE.move_to_end(key)
    while len(_BRIEFING_CACHE) > _BRIEFING_CACHE_MAX:
        _BRIEFING_CACHE.popitem(last=False)
    return key


def _briefing_response(bundle, build_id: str) -> dict:
    """Serialize the bundle for the browser: Pydantic self-serializes (case/dossier via the
    model's field_serializers); we only augment each figure with a browser-loadable image_url +
    an availability flag (mirrors _figure_dict). image_path is kept so the PDF renderer can read
    the file directly off the cached object."""
    data = bundle.model_dump(mode="json")
    for fig in data.get("figures", []):
        path = fig.get("image_path", "") or ""
        fig["image_url"] = _image_url(path)
        fig["image_available"] = _safe_image_path(path) is not None
    data["build_id"] = build_id
    return data


class BriefingBuildRequest(BaseModel):
    topic: str
    enrich: bool = True
    use_llm: bool = True
    use_prefs: bool = True


def _do_build_briefing(topic: str, enrich: bool, use_llm: bool, prefs=None):
    from neuro_caseboard.pipeline import build_briefing_bundle
    return build_briefing_bundle(topic, enrich=enrich,
                                 use_llm=None if use_llm else False, prefs=prefs)


@app.post("/api/briefing")
def briefing(req: BriefingBuildRequest):
    topic = (req.topic or "").strip()
    if not topic:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty topic"})

    from neuro_core.gpu_guard import GpuNotReadyError
    prefs = None
    if req.use_prefs:
        from neuro_caseboard.preferences import load_preferences, default_store_path
        prefs = load_preferences(default_store_path()) or None
    try:
        bundle = _do_build_briefing(topic, req.enrich, req.use_llm, prefs)
    except GpuNotReadyError as e:
        return JSONResponse(status_code=503,
                            content={"kind": "unavailable", "reason": f"GPU not ready: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"kind": "error", "error": f"{type(e).__name__}: {e}"})

    build_id = _cache_briefing(topic, req.enrich, req.use_llm, req.use_prefs, bundle)
    return _briefing_response(bundle, build_id)


class BriefingPdfRequest(BaseModel):
    build_id: str


@app.post("/api/briefing/pdf")
def briefing_pdf(req: BriefingPdfRequest):
    # exported == displayed: serve the CACHED bundle. The 7-call synthesis is nondeterministic,
    # so a rebuild would render different content than what the browser is showing. Miss -> honest
    # error telling the client to (re)build first, NOT a silent divergent rebuild.
    entry = _BRIEFING_CACHE.get(req.build_id or "")
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={"error": "no cached build for that build_id — POST /api/briefing first"})
    topic, bundle = entry

    from neuro_caseboard.operative_briefing_pdf import render_operative_briefing_pdf
    from neuro_caseboard.pipeline import _slug
    tmp_dir = Path(tempfile.mkdtemp(prefix="caseboard_briefing_pdf_"))
    pdf_path = tmp_dir / "operative-briefing.pdf"
    try:
        render_operative_briefing_pdf(bundle, pdf_path)
    except RuntimeError as e:
        # Plan 2 raises RuntimeError("renderer unavailable …") when Chromium/Playwright is absent.
        return JSONResponse(status_code=503, content={"error": f"{e}"})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"error": f"PDF render failed: {type(e).__name__}: {e}"})
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=f"{_slug(topic)}-operative-briefing.pdf")


# ---------------------------------------------------------------------------------------------
# Rehearsal: surgeon marks the board (wrong/missing/important) -> distil into profile-keyed
# operative preferences (persisted) -> rebuild the board with them applied. GET /api/preferences
# surfaces what is remembered (provenance: action, pattern, weight, source cases). Same engine
# calls as the CLI/Streamlit; never fabricates a board.
# ---------------------------------------------------------------------------------------------

class FeedbackMarkIn(BaseModel):
    mark: str
    text: str
    section: str = ""
    note: str = ""


class FeedbackRequest(BaseModel):
    topic: str
    profile: str = ""
    enrich: bool = False
    use_llm: bool = False
    items: list[FeedbackMarkIn]


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    topic = (req.topic or "").strip()
    if not topic:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty topic"})
    if not req.items:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "no marks"})

    from neuro_caseboard.pipeline import classify_profile
    from neuro_caseboard.feedback import CaseFeedback, FeedbackItem, target_file_for_heading
    from neuro_caseboard.preferences import (
        distill, load_preferences, save_preferences, default_store_path,
    )
    profile = req.profile or classify_profile(topic)
    try:
        items = [FeedbackItem(mark=m.mark, text=m.text,
                              target_file=target_file_for_heading(m.section), note=m.note)
                 for m in req.items]
    except ValueError as e:
        # Honest degradation: a malformed mark is a client error, not a 500.
        return JSONResponse(status_code=422, content={"kind": "error", "error": str(e)})
    fb = CaseFeedback(topic=topic, profile=profile, items=items)
    store = default_store_path()
    prefs = distill(fb, load_preferences(store))
    save_preferences(prefs, store)

    from neuro_core.gpu_guard import GpuNotReadyError
    try:
        dossier = _do_build(topic, req.enrich, req.use_llm, prefs)
    except GpuNotReadyError as e:
        return JSONResponse(status_code=503, content={"kind": "unavailable", "reason": f"GPU not ready: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"kind": "error", "error": f"{type(e).__name__}: {e}"})
    # Cache the rebuilt board so a later PDF export matches what the surgeon now sees (the board WITH
    # the marks applied), not the pre-feedback board.
    build_id = _cache_dossier(topic, req.enrich, req.use_llm, dossier)
    return {"kind": "dossier", "build_id": build_id, "topic": topic, "profile": profile,
            "remembered": len(prefs), "dossier": _dossier_dict(dossier)}


@app.get("/api/preferences")
def preferences() -> dict:
    from dataclasses import asdict
    from neuro_caseboard.preferences import load_preferences, default_store_path
    prefs = load_preferences(default_store_path())
    return {"kind": "preferences", "count": len(prefs), "preferences": [asdict(p) for p in prefs]}


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


# --- Static web SPA (single-process local deploy) --------------------------------------
# Serve the built React/Vite app (web/dist) so `uvicorn api.server:app` is the whole product:
# the redesigned console at "/", the engine at "/api/*". In dev you'd run `npm run dev` instead
# (Vite hot-reload + /api proxy); this catch-all just makes the *built* app the default the
# server hands out. The dist path is resolved per-request from NEURO_CASEBOARD_WEB_DIST (env)
# so deployments can relocate it and tests can point at a fixture.

def _web_dist() -> Path:
    """Resolve the built-SPA directory (override with NEURO_CASEBOARD_WEB_DIST)."""
    override = os.environ.get("NEURO_CASEBOARD_WEB_DIST")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "web" / "dist"


# Declared LAST so every explicit route above (all "/api/*", plus FastAPI's own "/docs",
# "/openapi.json") matches first; only non-API, non-doc paths fall through to the SPA.
@app.get("/{full_path:path}")
def _serve_spa(full_path: str):
    # Never let the SPA catch-all answer an unknown /api/* path — a typo'd endpoint must stay
    # an honest JSON 404, not silently render the HTML shell.
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    dist = _web_dist()
    index = dist / "index.html"
    if not index.is_file():
        # Honest degradation: the server (API) is up, but the web UI hasn't been built.
        return JSONResponse(status_code=503, content={
            "kind": "unavailable",
            "reason": "web UI not built — run `npm --prefix web run build` "
                      "(or `npm run dev` for hot-reload during development)",
        })

    # Serve a real built file when the path points at one (assets, favicon, …); otherwise fall
    # back to index.html so client-side routes (/ask, /build, /cards) work on a hard refresh.
    if full_path:
        candidate = (dist / full_path).resolve()
        dist_root = dist.resolve()
        # Path-traversal guard: the resolved file must stay inside the dist directory.
        if candidate.is_file() and (candidate == dist_root or dist_root in candidate.parents):
            return FileResponse(candidate)
    return FileResponse(index)
