# Operative Briefing Bundle — Plan 3: API + Web Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the already-built `OperativeBriefingBundle` contract (Plan 1, `briefing_model.py` + `pipeline.build_briefing_bundle`) and PDF renderer (Plan 2, `operative_briefing_pdf.py`) into the API and web surfaces — additive `POST /api/briefing` + `POST /api/briefing/pdf` with an LRU bundle cache, generated TypeScript types, and `Build.tsx` rebuilt as the three-surface briefing view.

**Architecture:** Additive only. Two new FastAPI endpoints reuse the existing `_image_url`/`_safe_image_path` figure-serving and the `_dossier_dict` serializer; a new `_BRIEFING_CACHE` (the same `OrderedDict` LRU pattern as `_DOSSIER_CACHE`) holds the real `OperativeBriefingBundle` object keyed by `schema_version + opts`, so the PDF endpoint serves *that cached bundle* (exported == displayed) and the figure renderer still reads `image_path` directly. TS types are generated from the Pydantic JSON schema by a Python script and guarded against drift by a pytest. `Build.tsx` renders the one-page briefing preview, a bounded figure gallery, the references page, and the existing dossier wrapped as a collapsible Evidence Audit.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2 (`model_json_schema`, `model_dump(mode="json")`), Playwright/Chromium (`briefing` extra, via Plan 2's renderer), React 18 + Vite + TypeScript + Tailwind v4, vitest.

## Global Constraints

- **Additive only.** `POST /api/briefing` + `POST /api/briefing/pdf` are new; **`/api/build*` is untouched**, the `Dossier` dataclass is untouched, **Ask is not touched**. (spec §1, §9; task)
- **`exported == displayed` is a cache-coherence property.** The 7-Flash synthesis is nondeterministic, so the PDF endpoint **serves the cached bundle by `build_id`** and renders that — it **never silently rebuilds**. Cache miss → honest error, not a fresh (divergent) build. (advisor; spec §9)
- **LRU cache keyed by `schema_version + opts`.** Reuse the `_DOSSIER_CACHE` `OrderedDict` pattern; the key includes `BRIEFING_SCHEMA_VERSION` so a schema bump can't collide with a stale entry. Store the **real `OperativeBriefingBundle`** (image_path intact). (spec §9)
- **Figures reuse `/api/figure?path=` + `_safe_image_path`.** Keep `image_path` in the model so Plan 2's `img_data_uri` still works; **augment only the dumped dict** with `image_url`/`image_available` (mirrors `_figure_dict`). (advisor; spec §9)
- **Generated TS covers the Pydantic core only.** `scripts/gen_briefing_types.py` walks `model_json_schema()`; the figure-view augmentation and the `dossier`/`case` (`Any`→`unknown`) seams are hand-maintained on top. The generator **raises on any JSON-schema construct it doesn't recognize** — that raise is what makes the drift-guard real. (advisor)
- **Drift guard is a pytest** (CLAUDE.md: pytest is the only CI gate; ruff/eslint/mypy are not). The test regenerates types in-memory and asserts equality with the checked-in `web/src/lib/briefingTypes.ts`. (advisor; CLAUDE.md)
- **`T#` (textbook) / `L#` (PubMed) namespaces stay distinct** on the references surface — never merged or renumbered. (spec §8, §11)
- **No citation markers or retrieved figures inside the one-page briefing preview** — the gallery and references are separate surfaces. (spec §1, §11)
- **Figure gallery uses Tailwind `sm:` responsive classes, never inline `gridTemplateColumns`** — web/ has no `useMediaQuery`, so inline grid stays N-up and clips on mobile (spec §10 requires mobile legibility). (memory: web-responsive-grid-gotcha)
- **Honest degradation.** Every endpoint forwards the engine's real result OR a real error (GPU-not-ready → 503, renderer-unavailable → honest JSON), never a fabricated briefing. (spec §9, §11; api/server.py convention)
- **CLAUDE.md test gotchas:** pytest is the gate; **never `pytest-xdist -n auto`**; `pytest.importorskip` for optional deps; scoped fast loop locally. **No CLI flag** (Plan 2 mentioned one; the task + spec §9/§10 do not — task wins).

---

## File Structure

- **Create:** `scripts/gen_briefing_types.py` — dumps `OperativeBriefingBundle.model_json_schema()` and walks it into TypeScript. Single responsibility: schema → `.ts` text.
- **Create:** `web/src/lib/briefingTypes.ts` — **generated** (checked in). The Pydantic-core interfaces consumed by the briefing components.
- **Create:** `tests/test_briefing_types_gen.py` — drift guard: regenerate in-memory, assert == checked-in file.
- **Modify:** `api/server.py` — add `_BRIEFING_CACHE`, `_briefing_response()`, `POST /api/briefing`, `POST /api/briefing/pdf`. Reuses `_image_url`, `_safe_image_path`, `_dossier_dict` already there.
- **Create:** `tests/test_api_briefing.py` — offline serialization + cache + endpoint tests (monkeypatch `build_briefing_bundle` / `render_operative_briefing_pdf`).
- **Modify:** `web/src/lib/api.ts` — `BriefingResponse` union, `buildBriefing()`, `fetchBriefingPdf()`; re-export the generated types.
- **Create:** `web/src/components/build/OperativeBriefingView.tsx` — the one-page briefing preview: prose sections, decision-algorithm node/branch list, treatment modalities, equipment plan, unknowns, disclaimer (internal subcomponents — one file).
- **Create:** `web/src/components/build/BriefingFigureGallery.tsx` — bounded scrollable high-yield gallery; reuses the existing figure lightbox.
- **Create:** `web/src/components/build/BriefingReferences.tsx` — `T#`/`L#` grouped references with the per-section support map.
- **Modify:** `web/src/pages/Build.tsx` — becomes the briefing surface: case header + export, briefing preview, gallery, references, collapsible Evidence Audit (existing `DossierView` wrapped in `<details>`), retained rehearsal.

**Untouched:** `briefing_model.py`, `briefing_synth.py`, `briefing_figures.py`, `operative_briefing_pdf.py`, `pipeline.py`, `exec_navy.py`, `web/src/pages/Ask.tsx`, `web/src/components/build/DossierView.tsx` (reused as-is).

### Public surface (consumed across tasks)

```python
# Task 1 (scripts/gen_briefing_types.py)
def generate_ts() -> str            # full briefingTypes.ts text, deterministic

# Task 2 (api/server.py)
_BRIEFING_CACHE: "OrderedDict[str, tuple[str, object]]"
def _briefing_key(topic, enrich, use_llm, use_prefs) -> str
def _cache_briefing(topic, enrich, use_llm, use_prefs, bundle) -> str   # build_id
def _briefing_response(bundle, build_id) -> dict    # model_dump + figure image_url augmentation
@app.post("/api/briefing")          # BriefingBuildRequest -> _briefing_response | honest error
@app.post("/api/briefing/pdf")      # BriefingPdfRequest   -> FileResponse | honest error
```

```typescript
// Task 4 (web/src/lib/api.ts)
export type BriefingResponse =
  | { kind: "briefing"; build_id: string; topic: string; case: unknown;
      briefing: OperativeBriefing; figures: BriefingFigureView[];
      references: BriefingReference[]; dossier: Dossier; provenance: BriefingProvenance }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }
export interface BriefingFigureView extends BriefingFigure { image_url: string | null; image_available: boolean }
export function buildBriefing(topic, opts, signal?): Promise<BriefingResponse>
export function fetchBriefingPdf(build_id, signal?): Promise<Blob>
```

---

## Task 1: TypeScript type generator + generated file + drift-guard test

**Files:**
- Create: `scripts/gen_briefing_types.py`
- Create: `web/src/lib/briefingTypes.ts` (generated, checked in)
- Test: `tests/test_briefing_types_gen.py`

**Interfaces:**
- Consumes: `neuro_caseboard.briefing_model.OperativeBriefingBundle.model_json_schema()`. The schema uses exactly these constructs (verified by dumping it): `type` (string/integer/boolean/array/object), `const` (Literal→string-literal), `enum` (Literal→union), `$ref`, `anyOf:[X,null]` (Optional→`X | null`), `anyOf:[{oneOf:[…],discriminator}, null]` (equipment union), `items` (array), `additionalProperties:true` (`meta`→`Record<string, unknown>`), and untyped props (`case`/`dossier`→`unknown`).
- Produces: `generate_ts() -> str` — the full `briefingTypes.ts` text. The drift-guard pytest asserts the checked-in file equals `generate_ts()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_types_gen.py
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TS_FILE = REPO / "web" / "src" / "lib" / "briefingTypes.ts"


def test_generated_ts_matches_checked_in_file():
    """The checked-in TS types must equal a fresh generation from the Pydantic schema.
    If this fails, run: python3 scripts/gen_briefing_types.py  (regenerates the file)."""
    from scripts.gen_briefing_types import generate_ts
    assert TS_FILE.read_text() == generate_ts(), (
        "briefingTypes.ts is stale — run `python3 scripts/gen_briefing_types.py`")


def test_generated_ts_has_core_interfaces():
    from scripts.gen_briefing_types import generate_ts
    ts = generate_ts()
    for name in ("OperativeBriefing", "BriefingItem", "BriefingFigure",
                 "BriefingReference", "BriefingProvenance", "DecisionAlgorithm"):
        assert f"export interface {name}" in ts
    # discriminated equipment union collapses to a named union type
    assert "export type EquipmentPlan =" in ts
    # Optional → `| null`; enum → string-literal union
    assert "DecisionAlgorithm | null" in ts
    assert '"critical" | "high" | "optional"' in ts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_briefing_types_gen.py -q`
Expected: FAIL — `ModuleNotFoundError: scripts.gen_briefing_types` (and the file doesn't exist).

- [ ] **Step 3: Write the generator**

```python
# scripts/gen_briefing_types.py
"""Generate web/src/lib/briefingTypes.ts from the OperativeBriefingBundle Pydantic schema.

The browser contract for the briefing surface is generated from the Python schema so it
cannot drift: a pytest (tests/test_briefing_types_gen.py) regenerates in-memory and diffs
against the checked-in file. Run this script to refresh the file after a model change:

    python3 scripts/gen_briefing_types.py

Scope: the Pydantic *core* only. The served JSON augments figures with image_url/
image_available and serializes `case`/`dossier` as opaque (Any -> unknown); those seams
are hand-maintained in web/src/lib/api.ts on top of these generated interfaces.
"""
from __future__ import annotations

from pathlib import Path

from neuro_caseboard.briefing_model import OperativeBriefingBundle

HEADER = (
    "// GENERATED by scripts/gen_briefing_types.py — DO NOT EDIT BY HAND.\n"
    "// Regenerate after a briefing_model.py change: python3 scripts/gen_briefing_types.py\n"
    "// Source of truth: OperativeBriefingBundle.model_json_schema() (Pydantic v2).\n\n"
)


def _ts_type(node: dict) -> str:
    """One JSON-schema node -> a TS type expression. Raises on any construct we don't emit,
    so a new model shape fails the drift-guard test instead of generating silent junk."""
    if "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]
    if "const" in node:
        return f'"{node["const"]}"'
    if "enum" in node:
        return " | ".join(f'"{v}"' for v in node["enum"])
    if "anyOf" in node:
        return " | ".join(_ts_type(s) for s in node["anyOf"])
    if "oneOf" in node:                      # discriminated union (equipment)
        return " | ".join(_ts_type(s) for s in node["oneOf"])
    t = node.get("type")
    if t == "null":
        return "null"
    if t == "array":
        return f"{_ts_type(node['items'])}[]"
    if t == "object":
        if node.get("additionalProperties"):
            return "Record<string, unknown>"
        return "Record<string, unknown>"
    if t == "string":
        return "string"
    if t == "integer" or t == "number":
        return "number"
    if t == "boolean":
        return "boolean"
    if not node or set(node) <= {"title", "default"}:   # untyped (Any) prop -> opaque
        return "unknown"
    raise ValueError(f"gen_briefing_types: unhandled schema node {node!r}")


def _interface(name: str, defn: dict) -> str:
    props = defn.get("properties", {})
    required = set(defn.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop, node in props.items():
        optional = "" if prop in required else "?"
        lines.append(f"  {prop}{optional}: {_ts_type(node)}")
    lines.append("}")
    return "\n".join(lines)


def generate_ts() -> str:
    schema = OperativeBriefingBundle.model_json_schema()
    out = [HEADER.rstrip("\n")]
    # Named $defs become interfaces, EXCEPT a pure discriminated `oneOf` collapses to a union
    # type alias (equipment). $defs are emitted in sorted order for a stable, diffable file.
    for name, defn in sorted(schema.get("$defs", {}).items()):
        out.append("")
        out.append(_interface(name, defn))
    # Equipment discriminated union -> named alias (read off the OperativeBriefing.equipment prop).
    equip = schema["$defs"]["OperativeBriefing"]["properties"]["equipment"]
    union = next(s for s in equip["anyOf"] if "oneOf" in s)
    members = " | ".join(m["$ref"].rsplit("/", 1)[-1] for m in union["oneOf"])
    out.append("")
    out.append(f"export type EquipmentPlan = {members}")
    # Top-level bundle (its own props: case/dossier are opaque, figures get a view type in api.ts).
    out.append("")
    out.append(_interface("OperativeBriefingBundle", schema))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "web" / "src" / "lib" / "briefingTypes.ts"
    target.write_text(generate_ts())
    print(f"wrote {target}")
```

- [ ] **Step 4: Generate the file, then run the test**

Run: `python3 scripts/gen_briefing_types.py && python3 -m pytest tests/test_briefing_types_gen.py -q`
Expected: writes `web/src/lib/briefingTypes.ts`, then PASS (2 tests). If `_ts_type` raises on a construct, fix the walker to handle exactly that construct (don't broaden it speculatively).

- [ ] **Step 5: Commit**

```bash
git add scripts/gen_briefing_types.py web/src/lib/briefingTypes.ts tests/test_briefing_types_gen.py
git commit -m "feat(briefing-api): generate TS types from Pydantic schema + drift-guard test (Plan 3 Task 1)"
```

---

## Task 2: `POST /api/briefing` — build, cache, serialize

**Files:**
- Modify: `api/server.py`
- Test: `tests/test_api_briefing.py`

**Interfaces:**
- Consumes: `pipeline.build_briefing_bundle(topic, *, use_llm, enrich, prefs)` (Plan 1), `OperativeBriefingBundle.model_dump(mode="json")`, existing `_image_url`/`_safe_image_path`. `BRIEFING_SCHEMA_VERSION` from `briefing_model`.
- Produces: `_BRIEFING_CACHE`, `_briefing_key`, `_cache_briefing`, `_briefing_response(bundle, build_id) -> dict`, and the `POST /api/briefing` route. `_briefing_response` returns `model_dump(mode="json")` with each `figures[i]` augmented by `image_url` + `image_available` derived from its `image_path`, and `build_id` injected.

- [ ] **Step 1: Write the failing tests** (offline — build a real bundle with the established fakes; the endpoint is exercised via a monkeypatched builder)

```python
# tests/test_api_briefing.py
import importlib

from fastapi.testclient import TestClient

import api.server as server
from neuro_caseboard.pipeline import build_briefing_bundle


class FakeSynth:
    def generate(self, system, user, images):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        if key == "equipment":
            return "positioning_monitoring: prone; SSEP\nrefs: T1\n"
        if key == "modalities":
            return "### ACDF\nrole: decompress\npreferred: yes\nrefs: T1\n"
        return f"[critical] {key} claim {{T1}}\n"


class TRec:
    def __init__(self, n):
        self.id = f"rec-{n}"; self.title = f"Youmans chapter {n}"; self.source = "corpus"
        self.text = f"passage {n}"; self.metadata = {"citation": f"Youmans p.{n}", "book": "Youmans", "page": n}


class TextRetriever:
    def retrieve(self, query, top_n=6, **kwargs):
        return [TRec(1)]


def _bundle():
    return build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                                 fig_retriever=None, synth_client=FakeSynth(), literature=False)


def test_briefing_response_augments_figures_and_injects_build_id():
    b = _bundle()
    # give one figure a path so the augmentation has something to resolve
    from neuro_caseboard.briefing_model import BriefingFigure
    b.figures = [BriefingFigure(fig_id="BF1", image_path="/no/such.png", caption="x")]
    resp = server._briefing_response(b, "abc123")
    assert resp["kind"] == "briefing" and resp["build_id"] == "abc123"
    fig = resp["figures"][0]
    assert "image_url" in fig and "image_available" in fig
    assert fig["image_url"].startswith("/api/figure?path=")     # browser-loadable URL
    assert fig["image_available"] is False                      # bogus path -> not served
    assert "image_path" in fig                                  # original kept (PDF renderer reads it)


def test_briefing_cache_is_lru_bounded():
    server._BRIEFING_CACHE.clear()
    for i in range(server._BRIEFING_CACHE_MAX + 3):
        server._cache_briefing(f"topic {i}", True, True, True, object())
    assert len(server._BRIEFING_CACHE) == server._BRIEFING_CACHE_MAX


def test_post_briefing_returns_serialized_bundle(monkeypatch):
    b = _bundle()
    monkeypatch.setattr(server, "_do_build_briefing", lambda *a, **k: b)
    client = TestClient(server.app)
    r = client.post("/api/briefing", json={"topic": "C5-6 ACDF"})
    assert r.status_code == 200
    data = r.json()
    assert data["kind"] == "briefing" and data["build_id"]
    assert data["briefing"]["sections"]                          # real briefing rode through
    assert data["build_id"] in server._BRIEFING_CACHE           # cached for the PDF endpoint


def test_post_briefing_empty_topic_is_422():
    client = TestClient(server.app)
    r = client.post("/api/briefing", json={"topic": "  "})
    assert r.status_code == 422 and r.json()["kind"] == "error"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_api_briefing.py -q`
Expected: FAIL — `AttributeError: module 'api.server' has no attribute '_briefing_response'`.

- [ ] **Step 3: Implement** (append to `api/server.py`, after the Build section ~line 547, before the Rehearsal section)

```python
# api/server.py  (append after build_pdf, before the Rehearsal section)

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_api_briefing.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add api/server.py tests/test_api_briefing.py
git commit -m "feat(briefing-api): POST /api/briefing — build, LRU cache, browser-augmented JSON (Plan 3 Task 2)"
```

---

## Task 3: `POST /api/briefing/pdf` — serve the cached bundle

**Files:**
- Modify: `api/server.py`
- Test: `tests/test_api_briefing.py`

**Interfaces:**
- Consumes: `_BRIEFING_CACHE` (Task 2), `operative_briefing_pdf.render_operative_briefing_pdf(bundle, out_path, *, synth_client=None) -> str` (Plan 2), `pipeline._slug`.
- Produces: `POST /api/briefing/pdf` route. Requires a cached `build_id`; **miss → honest 404** (never a silent rebuild — that would break exported==displayed). Renderer-unavailable (`RuntimeError("renderer unavailable …")` from Plan 2 when Chromium/Playwright is absent) → honest 503.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_briefing.py  (append)

def test_briefing_pdf_requires_cached_build_id():
    client = TestClient(server.app)
    r = client.post("/api/briefing/pdf", json={"build_id": "does-not-exist"})
    assert r.status_code == 404
    assert "build" in r.json()["error"].lower()                 # honest "no cached build" message


def test_briefing_pdf_serves_cached_bundle(monkeypatch, tmp_path):
    b = _bundle()
    build_id = server._cache_briefing("C5-6 ACDF", True, True, True, b)
    seen = {}

    def fake_render(bundle, out_path, *, synth_client=None):
        seen["bundle"] = bundle
        from pathlib import Path
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return str(out_path)

    monkeypatch.setattr("neuro_caseboard.operative_briefing_pdf.render_operative_briefing_pdf",
                        fake_render)
    client = TestClient(server.app)
    r = client.post("/api/briefing/pdf", json={"build_id": build_id})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert seen["bundle"] is b                                  # the CACHED object, not a rebuild


def test_briefing_pdf_renderer_unavailable_is_503(monkeypatch):
    b = _bundle()
    build_id = server._cache_briefing("C5-6 ACDF", True, True, True, b)

    def boom(bundle, out_path, *, synth_client=None):
        raise RuntimeError("renderer unavailable: needs the briefing extra")

    monkeypatch.setattr("neuro_caseboard.operative_briefing_pdf.render_operative_briefing_pdf", boom)
    client = TestClient(server.app)
    r = client.post("/api/briefing/pdf", json={"build_id": build_id})
    assert r.status_code == 503
    assert "renderer unavailable" in r.json()["error"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_api_briefing.py -k pdf -q`
Expected: FAIL — `/api/briefing/pdf` not found (404 from the SPA catch-all returns JSON `{"detail": "Not Found"}`, so the assert on `error` fails) → confirms the route is missing.

- [ ] **Step 3: Implement** (append after the `/api/briefing` route)

```python
# api/server.py  (append after the briefing() route)

class BriefingPdfRequest(BaseModel):
    build_id: str


@app.post("/api/briefing/pdf")
def briefing_pdf(req: BriefingPdfRequest):
    # exported == displayed: serve the CACHED bundle. The 7-call synthesis is nondeterministic,
    # so a rebuild would render different content than what the browser is showing. Miss -> honest
    # error telling the client to (re)build first, NOT a silent divergent rebuild.
    entry = _BRIEFING_CACHE.get(req.build_id or "")
    if entry is None:
        return JSONResponse(status_code=404,
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
```

> **ponytail:** the renderer is called with `synth_client=None`, so the fit ladder skips the optional LLM-compress rung. It still converges to ≤2 pages mechanically (Plan 2 Task 4). Wire a live `briefing_synth_client()` here only if real briefings are seen overflowing past the trim rung — they don't (critical core is small).

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_api_briefing.py -q`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add api/server.py tests/test_api_briefing.py
git commit -m "feat(briefing-api): POST /api/briefing/pdf serves the cached bundle (exported == displayed) (Plan 3 Task 3)"
```

---

## Task 4: Web API client — `buildBriefing` + `fetchBriefingPdf` + types

**Files:**
- Modify: `web/src/lib/api.ts`
- (No vitest: thin fetch wrappers mirror the existing untested `buildDossier`/`fetchBuildPdf`; verified by `tsc -b` in Task 7.)

**Interfaces:**
- Consumes: generated `web/src/lib/briefingTypes.ts` (Task 1), existing `Dossier` interface in `api.ts`.
- Produces: re-exported briefing interfaces, `BriefingFigureView`, `BriefingResponse` union, `buildBriefing()`, `fetchBriefingPdf()`.

- [ ] **Step 1: Add the types + client (append to `web/src/lib/api.ts`)**

```typescript
// ----- Briefing (Operative Briefing Bundle) --------------------------------------------------
// Core shapes are generated from the Pydantic schema (briefingTypes.ts). The served JSON adds
// two hand-maintained seams: figures gain a browser image_url/availability, and `dossier` is the
// existing Dossier interface above (the Pydantic model serializes it as opaque Any).

import type {
  OperativeBriefing,
  BriefingFigure,
  BriefingReference,
  BriefingProvenance,
  BriefingSection,
  BriefingItem,
  TreatmentModality,
  DecisionAlgorithm,
  AlgoNode,
  AlgoEdge,
  EquipmentPlan,
} from "@/lib/briefingTypes"

export type {
  OperativeBriefing, BriefingFigure, BriefingReference, BriefingProvenance,
  BriefingSection, BriefingItem, TreatmentModality, DecisionAlgorithm,
  AlgoNode, AlgoEdge, EquipmentPlan,
}

export interface BriefingFigureView extends BriefingFigure {
  image_url: string | null
  image_available: boolean
}

export type BriefingResponse =
  | {
      kind: "briefing"
      build_id: string
      topic: string
      case: unknown
      briefing: OperativeBriefing
      figures: BriefingFigureView[]
      references: BriefingReference[]
      dossier: Dossier
      provenance: BriefingProvenance
    }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }

export async function buildBriefing(
  topic: string,
  opts: { enrich: boolean; use_llm: boolean; use_prefs?: boolean },
  signal?: AbortSignal,
): Promise<BriefingResponse> {
  const res = await fetch("/api/briefing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, enrich: opts.enrich, use_llm: opts.use_llm, use_prefs: opts.use_prefs ?? true }),
    signal,
  })
  const data = (await res.json().catch(() => null)) as BriefingResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

/** Fetch the briefing PDF for a cached build_id (no rebuild — exported == displayed). */
export async function fetchBriefingPdf(build_id: string, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch("/api/briefing/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ build_id }),
    signal,
  })
  if (!res.ok) {
    const msg = await res.json().then((d) => d?.error).catch(() => null)
    throw new Error(msg || `Briefing PDF export failed (${res.status})`)
  }
  return await res.blob()
}
```

- [ ] **Step 2: Typecheck the new client**

Run: `cd web && npx tsc -b --noEmit 2>&1 | head -30 || true`
Expected: no errors referencing `api.ts`/`briefingTypes.ts`. (A clean `tsc -b` is the gate in Task 7.)

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat(briefing-web): typed briefing API client (buildBriefing, fetchBriefingPdf) (Plan 3 Task 4)"
```

---

## Task 5: Briefing view components

**Files:**
- Create: `web/src/components/build/OperativeBriefingView.tsx`
- Create: `web/src/components/build/BriefingFigureGallery.tsx`
- Create: `web/src/components/build/BriefingReferences.tsx`
- Test: `web/src/components/build/briefingRefs.test.ts` (one pure helper — the T#/L# split)

**Interfaces:**
- Consumes: `OperativeBriefing`, `BriefingFigureView`, `BriefingReference` from `@/lib/api`; existing UI atoms in `@/components/ui`; the figure lightbox pattern used by `@/components/ask/FigureGrid` (reused — see Step 1).
- Produces: `<OperativeBriefingView briefing={…} />`, `<BriefingFigureGallery figures={…} />`, `<BriefingReferences references={…} />`, and `splitRefs(refs) -> { textbook, pubmed }`.

- [ ] **Step 1: Locate the existing lightbox** (reuse, don't rebuild — spec §10, PR #60)

Run: `grep -rn "dialog\|lightbox\|showModal" web/src/components/ask/FigureGrid.tsx`
Expected: confirms the `<dialog>`/`showModal()` lightbox to mirror in the gallery. If `FigureGrid` already takes a `Figure[]`-like prop and renders a grid + lightbox, the gallery can wrap a bounded-scroll container around the same markup pattern. Use whichever it exposes; do **not** introduce a new modal library.

- [ ] **Step 2: Write the failing test** (the one piece of real logic: the namespace split)

```typescript
// web/src/components/build/briefingRefs.test.ts
import { describe, it, expect } from "vitest"
import { splitRefs } from "./BriefingReferences"
import type { BriefingReference } from "@/lib/api"

const refs: BriefingReference[] = [
  { ref_id: "T1", kind: "textbook", citation: "Youmans ch.12", meta: {}, sections: ["pathology"] },
  { ref_id: "L1", kind: "pubmed", citation: "Smith 2024", meta: { pmid: "123" }, sections: ["management"] },
  { ref_id: "T2", kind: "textbook", citation: "Rhoton 2002", meta: {}, sections: ["technique"] },
]

describe("splitRefs", () => {
  it("keeps T# and L# namespaces distinct", () => {
    const { textbook, pubmed } = splitRefs(refs)
    expect(textbook.map((r) => r.ref_id)).toEqual(["T1", "T2"])
    expect(pubmed.map((r) => r.ref_id)).toEqual(["L1"])
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd web && npx vitest run src/components/build/briefingRefs.test.ts 2>&1 | tail -20`
Expected: FAIL — cannot import `splitRefs` (file/function not defined).

- [ ] **Step 4: Implement the three components**

`web/src/components/build/OperativeBriefingView.tsx` — the one-page briefing preview. **No `<img>`, no `[T#]`/`[L#]` markers** (the gallery + references are separate surfaces). Decision algorithm is a node/branch list (web-themed; the PDF carries the SVG flowchart).

```tsx
// web/src/components/build/OperativeBriefingView.tsx
import type {
  OperativeBriefing, BriefingSection, TreatmentModality, EquipmentPlan, DecisionAlgorithm,
} from "@/lib/api"

function Section({ section }: { section: BriefingSection }) {
  if (!section.items.length && !section.note) return null
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">{section.title}</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {section.items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm leading-relaxed text-foreground">
            <span aria-hidden className="select-none text-primary-ink">—</span>
            <span>
              {it.text}
              {it.unsupported && (
                <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-amber-ink">
                  clinician-verify
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {section.note && <p className="mt-1.5 text-xs italic text-muted-foreground">{section.note}</p>}
    </div>
  )
}

function Algorithm({ algo }: { algo: DecisionAlgorithm }) {
  if (!algo.nodes.length) return null
  const label = (id: string) => algo.nodes.find((n) => n.id === id)?.label ?? id
  const ids = new Set(algo.nodes.map((n) => n.id))
  const edges = algo.edges.filter((e) => ids.has(e.src) && ids.has(e.dst))
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">Decision algorithm</h3>
      <div className="mt-2 flex flex-col gap-2">
        {algo.nodes
          .filter((n) => edges.some((e) => e.src === n.id))
          .map((n) => (
            <div key={n.id} className="rounded-md border border-border bg-secondary/40 p-2.5">
              <p className="text-sm font-semibold text-foreground">{n.label}</p>
              <ul className="mt-1 flex flex-col gap-0.5">
                {edges.filter((e) => e.src === n.id).map((e, i) => (
                  <li key={i} className="font-mono text-xs text-muted-foreground">
                    {e.condition ? <span className="text-primary-ink">{e.condition} → </span> : "→ "}
                    {label(e.dst)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
      </div>
    </div>
  )
}

function Modalities({ mods }: { mods: TreatmentModality[] }) {
  if (!mods.length) return null
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">Treatment options</h3>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {mods.map((m, i) => (
          <div key={i} className={`rounded-md border bg-secondary/40 p-3 ${m.preferred ? "border-success" : "border-border"}`}>
            <p className="text-sm font-bold text-foreground">
              {m.name}
              {m.preferred && <span className="ml-2 font-mono text-[10px] uppercase text-success-ink">preferred</span>}
            </p>
            {m.role && <p className="mt-0.5 text-xs text-muted-foreground">{m.role}</p>}
            <ul className="mt-1.5 flex flex-col gap-0.5 text-xs text-foreground">
              {m.advantages.map((a, j) => <li key={`a${j}`}>+ {a}</li>)}
              {m.limitations.map((l, j) => <li key={`l${j}`} className="text-muted-foreground">− {l}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function Equipment({ equipment }: { equipment: EquipmentPlan }) {
  // Generic: render every non-empty string-list field; skip discriminator + source_refs.
  const rows = Object.entries(equipment).filter(
    ([k, v]) => k !== "kind" && k !== "source_refs" && Array.isArray(v) && v.length,
  ) as [string, string[]][]
  if (!rows.length) return null
  const human = (k: string) => k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <div className="border-t border-border pt-3">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">
        Equipment · {equipment.kind}
      </h3>
      <div className="mt-2 flex flex-col gap-1.5">
        {rows.map(([k, vals]) => (
          <div key={k} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
            <span className="shrink-0 font-mono text-xs font-semibold text-muted-foreground sm:w-44">{human(k)}</span>
            <span className="text-sm text-foreground">{vals.join("; ")}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function OperativeBriefingView({ briefing }: { briefing: OperativeBriefing }) {
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5">
      <div>
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-primary-ink">
          Operative Briefing
        </p>
        <h2 className="mt-1 font-display text-2xl font-bold tracking-tight text-foreground">{briefing.title}</h2>
      </div>
      {briefing.sections.map((s) => <Section key={s.key} section={s} />)}
      {briefing.algorithm && <Algorithm algo={briefing.algorithm} />}
      <Modalities mods={briefing.modalities} />
      {briefing.equipment && <Equipment equipment={briefing.equipment} />}
      {briefing.unknowns.length > 0 && (
        <div className="border-l-2 border-amber pl-3 text-xs text-muted-foreground">
          <span className="font-bold text-foreground">Case-specific unknowns: </span>
          {briefing.unknowns.join(" · ")}
        </div>
      )}
      {briefing.disclaimer && (
        <p className="border-t border-border pt-3 font-mono text-[10px] text-muted-foreground">{briefing.disclaimer}</p>
      )}
    </div>
  )
}
```

`web/src/components/build/BriefingFigureGallery.tsx` — bounded scroll region, **Tailwind `sm:` grid** (never inline `gridTemplateColumns`), figure lightbox reused.

```tsx
// web/src/components/build/BriefingFigureGallery.tsx
import { useRef, useState } from "react"
import type { BriefingFigureView } from "@/lib/api"

export default function BriefingFigureGallery({ figures }: { figures: BriefingFigureView[] }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [active, setActive] = useState<BriefingFigureView | null>(null)
  if (!figures.length) return null

  const open = (f: BriefingFigureView) => {
    if (!f.image_available) return
    setActive(f)
    dialogRef.current?.showModal()
  }

  return (
    <section className="flex flex-col gap-3">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-primary-ink">
        High-yield figures · {figures.length}
      </p>
      {/* Bounded scroll region — responsive grid via Tailwind sm:, NOT inline gridTemplateColumns. */}
      <div className="max-h-[28rem] overflow-y-auto rounded-2xl border border-border bg-card p-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {figures.map((f) => (
            <figure key={f.fig_id} className="overflow-hidden rounded-xl border border-border bg-secondary/40">
              {f.image_available ? (
                <button type="button" onClick={() => open(f)} className="block w-full" aria-label={`Enlarge ${f.fig_id}`}>
                  <img src={f.image_url ?? ""} alt={f.caption} className="max-h-56 w-full object-contain" />
                </button>
              ) : (
                <div className="flex h-32 items-center justify-center bg-muted text-xs text-muted-foreground">
                  image unavailable
                </div>
              )}
              <figcaption className="p-3 text-xs leading-relaxed text-muted-foreground">
                <span className="font-mono font-bold text-primary-ink">{f.fig_id}</span> {f.caption}
                {f.citation && <span className="mt-1 block text-[11px] text-muted-foreground/80">{f.citation}</span>}
              </figcaption>
            </figure>
          ))}
        </div>
      </div>

      <dialog
        ref={dialogRef}
        onClick={(e) => { if (e.target === dialogRef.current) dialogRef.current?.close() }}
        className="m-auto max-w-3xl rounded-xl bg-card p-0 backdrop:bg-black/70"
      >
        {active && (
          <div className="flex flex-col">
            <img src={active.image_url ?? ""} alt={active.caption} className="max-h-[70vh] w-full object-contain" />
            <div className="p-4">
              <p className="text-sm text-foreground">
                <span className="font-mono font-bold text-primary-ink">{active.fig_id}</span> {active.caption}
              </p>
              {active.citation && <p className="mt-1 text-xs text-muted-foreground">{active.citation}</p>}
              <button
                type="button"
                onClick={() => dialogRef.current?.close()}
                className="mt-3 rounded-md border border-border px-3 py-1 font-mono text-xs text-muted-foreground"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </dialog>
    </section>
  )
}
```

`web/src/components/build/BriefingReferences.tsx` — `T#`/`L#` distinct groups + support map.

```tsx
// web/src/components/build/BriefingReferences.tsx
import type { BriefingReference } from "@/lib/api"

export function splitRefs(refs: BriefingReference[]): {
  textbook: BriefingReference[]
  pubmed: BriefingReference[]
} {
  return {
    textbook: refs.filter((r) => r.kind === "textbook"),
    pubmed: refs.filter((r) => r.kind === "pubmed"),
  }
}

function refExtra(meta: Record<string, unknown>): string {
  return (["pmid", "doi", "url", "page", "book"] as const)
    .map((k) => meta?.[k])
    .filter(Boolean)
    .map(String)
    .join(" · ")
}

function RefList({ title, refs }: { title: string; refs: BriefingReference[] }) {
  if (!refs.length) return null
  return (
    <div>
      <h3 className="font-display text-sm font-bold text-foreground">{title}</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {refs.map((r) => {
          const extra = refExtra(r.meta as Record<string, unknown>)
          return (
            <li key={r.ref_id} className="text-sm text-foreground">
              <span className="font-mono text-xs font-bold text-primary-ink">{r.ref_id}</span> {r.citation}
              {extra && <span className="text-muted-foreground"> · {extra}</span>}
              {r.sections.length > 0 && (
                <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                  supports: {r.sections.join(", ")}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function BriefingReferences({ references }: { references: BriefingReference[] }) {
  if (!references.length) return null
  const { textbook, pubmed } = splitRefs(references)
  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-primary-ink">
        References &amp; Evidence
      </p>
      <RefList title="Textbook sources" refs={textbook} />
      <RefList title="Contemporary literature" refs={pubmed} />
    </section>
  )
}
```

- [ ] **Step 5: Run the helper test**

Run: `cd web && npx vitest run src/components/build/briefingRefs.test.ts 2>&1 | tail -20`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/build/OperativeBriefingView.tsx web/src/components/build/BriefingFigureGallery.tsx web/src/components/build/BriefingReferences.tsx web/src/components/build/briefingRefs.test.ts
git commit -m "feat(briefing-web): briefing view, figure gallery, references components (Plan 3 Task 5)"
```

---

## Task 6: `Build.tsx` becomes the briefing surface

**Files:**
- Modify: `web/src/pages/Build.tsx`
- Test: typecheck + existing vitest (Task 7).

**Interfaces:**
- Consumes: `buildBriefing`, `fetchBriefingPdf`, `BriefingResponse` (Task 4); `OperativeBriefingView`, `BriefingFigureGallery`, `BriefingReferences` (Task 5); existing `DossierView` (reused, wrapped) + rehearsal helpers already in `Build.tsx`.
- Produces: the rebuilt briefing page. The dossier audit + rehearsal flow are **preserved**, wrapped in a collapsible `<details>` ("Evidence Audit") below the briefing surfaces.

- [ ] **Step 1: Rewrite `Build.tsx`** (full file — it switches from `buildDossier`/`BuildResponse` to `buildBriefing`/`BriefingResponse`; the dossier now rides inside the briefing response, so rehearsal still works off `resp.dossier`)

```tsx
// web/src/pages/Build.tsx
import { useEffect, useRef, useState } from "react"
import {
  buildBriefing,
  fetchBriefingPdf,
  submitFeedback,
  type BriefingResponse,
  type FeedbackItemIn,
  type DossierClaim,
} from "@/lib/api"
import { Button, Eyebrow, Card } from "@/components/ui"
import PipelineLoader from "@/components/PipelineLoader"
import OperativeBriefingView from "@/components/build/OperativeBriefingView"
import BriefingFigureGallery from "@/components/build/BriefingFigureGallery"
import BriefingReferences from "@/components/build/BriefingReferences"
import DossierView, { type ClaimMark, type ClaimFilter } from "@/components/build/DossierView"
import RememberedPanel from "@/components/build/RememberedPanel"

const HINTS = [
  "left retrosigmoid vestibular schwannoma",
  "C5-6 ACDF",
  "right carotid endarterectomy",
  "ruptured ACoA aneurysm clipping",
  "L4-5 TLIF for spondylolisthesis",
]

const BUILD_STEPS = [
  "Designing the case-specific question set…",
  "Retrieving grounded passages per section…",
  "Synthesizing the operative briefing (7 sections)…",
  "Selecting high-yield figures + resolving references…",
]

export default function Build() {
  const [topic, setTopic] = useState("")
  const [submitted, setSubmitted] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [resp, setResp] = useState<BriefingResponse | null>(null)
  const [netError, setNetError] = useState<string | null>(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  const [rehearsal, setRehearsal] = useState(false)
  const [marks, setMarks] = useState<FeedbackItemIn[]>([])
  const [remembered, setRemembered] = useState<number | null>(null)
  const [filterActive] = useState<ClaimFilter>("all")

  const onMark = (heading: string, claim: DossierClaim, mark: ClaimMark) =>
    setMarks((prev) => {
      const isClaim = (x: FeedbackItemIn) =>
        x.section === heading && x.text === claim.text && (x.mark === "wrong" || x.mark === "important")
      const without = prev.filter((x) => !isClaim(x))
      const had = prev.some((x) => isClaim(x) && x.mark === mark)
      return had ? without : [...without, { mark, text: claim.text, section: heading }]
    })
  const markOf = (heading: string, claim: DossierClaim): ClaimMark | null => {
    const m = marks.find(
      (x) => x.section === heading && x.text === claim.text && (x.mark === "wrong" || x.mark === "important"),
    )
    return (m?.mark as ClaimMark) ?? null
  }
  const onMissing = (heading: string, text: string) =>
    setMarks((prev) => [...prev, { mark: "missing", text, section: heading }])

  async function remember() {
    if (resp?.kind !== "briefing" || !marks.length) return
    setRemembered(null)
    const r = await submitFeedback(resp.topic, marks, { enrich: true, use_llm: true })
    if (r.kind === "dossier") {
      // The feedback lane rebuilds the dossier; fold it back into the briefing response so the
      // Evidence Audit reflects the updated board (the briefing prose is unchanged by marks).
      setResp({ ...resp, dossier: r.dossier })
      setRemembered(r.remembered)
      setMarks([])
    } else {
      setNetError(r.kind === "unavailable" ? r.reason : r.error)
    }
  }

  useEffect(() => () => ctrlRef.current?.abort(), [])

  async function run(t: string) {
    const text = t.trim()
    if (!text || loading) return
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setSubmitted(text)
    setTopic(text)
    setResp(null)
    setNetError(null)
    setPdfError(null)
    setRemembered(null)
    setMarks([])
    setLoading(true)
    try {
      const r = await buildBriefing(text, { enrich: true, use_llm: true }, ctrl.signal)
      if (!ctrl.signal.aborted) setResp(r)
    } catch (e) {
      const err = e as { name?: string; message?: string }
      if (err?.name !== "AbortError") setNetError(err?.message ?? String(e))
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }

  async function onDownloadPdf() {
    if (resp?.kind !== "briefing" || pdfLoading) return
    setPdfLoading(true)
    setPdfError(null)
    try {
      const blob = await fetchBriefingPdf(resp.build_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${resp.topic.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-operative-briefing.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setPdfError((e as Error).message)
    } finally {
      setPdfLoading(false)
    }
  }

  const liveMsg = loading
    ? ""
    : netError
      ? "Request failed."
      : resp
        ? resp.kind === "briefing"
          ? `Operative briefing ready: ${resp.briefing.title}.`
          : resp.kind === "unavailable"
            ? "Engine temporarily unavailable."
            : "Engine error."
        : ""

  return (
    <div className="flex flex-col gap-6">
      <div aria-live="polite" className="sr-only">{liveMsg}</div>

      <header>
        <Eyebrow accent>Build · Operative briefing</Eyebrow>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-foreground">
          Operative briefing
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          A one-page, attending-level briefing for the exact case — pathology, management, technique,
          risks &amp; equipment — with a high-yield figure gallery and a grounded references page.
          Decision-support only; verify against primary sources.
        </p>
      </header>

      <form
        onSubmit={(e) => { e.preventDefault(); void run(topic) }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder='e.g. "ruptured ACoA aneurysm clipping"'
          className="field flex-1"
          disabled={loading}
          autoFocus
        />
        <Button type="submit" disabled={loading || !topic.trim()} className="sm:px-7 sm:py-3">
          {loading ? "Building…" : "Build briefing"}
        </Button>
      </form>

      {!submitted && !loading && (
        <div className="flex flex-wrap gap-2">
          {HINTS.map((h) => (
            <button key={h} onClick={() => void run(h)} className="chip">{h}</button>
          ))}
        </div>
      )}

      {loading && (
        <PipelineLoader
          steps={BUILD_STEPS}
          bars={7}
          estimate="Usually 1–4 minutes — a full operative briefing is a lot of retrieval + synthesis."
        />
      )}

      {netError && !loading && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-destructive">Request failed</p>
          <p className="mt-1 text-muted-foreground">{netError}</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">Is the engine wrapper running on :8001?</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "error" && (
        <Card className="p-5 text-sm">
          <p className="font-bold text-destructive">Engine error</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{resp.error}</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "unavailable" && (
        <Card className="bg-muted p-5 text-sm">
          <p className="font-bold text-foreground">Temporarily unavailable</p>
          <p className="mt-1 text-muted-foreground">{resp.reason}</p>
        </Card>
      )}

      {resp && !loading && resp.kind === "briefing" && (
        <div className="flex flex-col gap-6">
          {/* Case header + export / rehearsal toggle */}
          <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-border bg-card p-5">
            <div className="flex min-w-0 flex-col gap-2">
              <span className="w-fit rounded-full border border-primary/30 bg-primary/10 px-3 py-1 font-mono text-[10px] text-primary-ink">
                {resp.topic}
              </span>
              {resp.provenance.degraded && (
                <span className="font-mono text-[10px] text-amber-ink">
                  degraded: {resp.provenance.reason || "partial evidence"}
                </span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => void onDownloadPdf()}
                disabled={pdfLoading}
                className="rounded-lg border border-border px-4 py-2 font-mono text-xs text-muted-foreground disabled:opacity-50"
              >
                {pdfLoading ? "Rendering…" : "Export PDF"}
              </button>
              <Button onClick={() => setRehearsal(!rehearsal)}>
                {rehearsal ? "Exit Rehearsal" : "Rehearse"}
              </Button>
            </div>
          </div>
          {pdfError && <span className="text-xs text-destructive">{pdfError}</span>}

          {/* 1 — one-page operative briefing */}
          <OperativeBriefingView briefing={resp.briefing} />

          {/* 2 — high-yield figure gallery */}
          <BriefingFigureGallery figures={resp.figures} />

          {/* 3 — references / evidence */}
          <BriefingReferences references={resp.references} />

          {/* Rehearsal controls */}
          {rehearsal && (
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void remember()} disabled={!marks.length}>
                Remember {marks.length || ""} mark{marks.length === 1 ? "" : "s"} &amp; update board
              </Button>
              <span className="text-xs text-muted-foreground">
                Mark claims ✗ wrong / ★ important, or add a missing consideration per section.
              </span>
            </div>
          )}
          {remembered !== null && <RememberedPanel remembered={remembered} />}

          {/* 4 — expandable full evidence audit (the existing claim-card dossier, preserved) */}
          <details className="rounded-2xl border border-border bg-card p-5">
            <summary className="cursor-pointer font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-primary-ink">
              Evidence Audit · full claim-card dossier ({resp.dossier.sections.length} sections)
            </summary>
            <div className="mt-4">
              <DossierView
                dossier={resp.dossier}
                filter={filterActive}
                rehearsal={rehearsal}
                markOf={markOf}
                onMark={onMark}
                onMissing={onMissing}
              />
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc -b --noEmit 2>&1 | head -40`
Expected: clean (no errors). Fix any prop-name mismatch against the real `DossierView`/`ui` exports surfaced here (e.g. if `Eyebrow`/`Card` import paths differ, align to the existing ones used in the old `Build.tsx`).

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Build.tsx
git commit -m "feat(briefing-web): Build.tsx becomes the operative-briefing surface (Plan 3 Task 6)"
```

---

## Task 7: Full verification (completion gate — spec §12, §14)

**Files:** none (verification only).

- [ ] **Step 1: Python collection precheck** (CLAUDE.md: a bad import aborts the whole suite)

Run: `python3 -m pytest tests/test_api_briefing.py tests/test_briefing_types_gen.py --collect-only -q`
Expected: collects cleanly, no import error.

- [ ] **Step 2: New Python tests green**

Run: `python3 -m pytest tests/test_api_briefing.py tests/test_briefing_types_gen.py -q`
Expected: PASS (all).

- [ ] **Step 3: Scoped Python regression** (the briefing engine + server were the only Python touched)

Run: `python3 -m pytest tests/test_briefing_model.py tests/test_briefing_pipeline.py tests/test_operative_briefing_pdf.py tests/test_server_spa.py -q`
Expected: PASS (Plans 1–2 + SPA serving unaffected).

- [ ] **Step 4: Frontend gate** — typecheck, build, unit tests

Run: `cd web && npm run lint && npx tsc -b --noEmit && npm run test && npm run build 2>&1 | tail -20`
Expected: eslint clean, `tsc` clean, vitest all pass (incl. the new `splitRefs` test), `vite build` succeeds (produces `web/dist`).

- [ ] **Step 5: Manual end-to-end** (this box has Vertex ADC + corpus + Chromium)

```bash
# terminal 1
CORPUS_DIR=/home/michael/textbook_pdfs python3 -m uvicorn api.server:app --port 8001
# terminal 2 — build a briefing, then export its cached PDF
BID=$(curl -s localhost:8001/api/briefing -H 'Content-Type: application/json' \
  -d '{"topic":"ruptured ACoA aneurysm clipping"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["build_id"])')
echo "build_id=$BID"
curl -s localhost:8001/api/briefing/pdf -H 'Content-Type: application/json' \
  -d "{\"build_id\":\"$BID\"}" -o /home/michael/.claude/jobs/5596a340/tmp/briefing_acom.pdf
# count pages with the renderer's own helper (uses fitz/PyMuPDF — a declared core dep; pypdf is not)
python3 -c "from neuro_caseboard.operative_briefing_pdf import count_pdf_pages; print('pages:', count_pdf_pages(open('/home/michael/.claude/jobs/5596a340/tmp/briefing_acom.pdf','rb').read()))"
```

Expected: `/api/briefing` returns `kind:"briefing"` with `briefing.sections`, `figures` (5–10), `references` (T#+L#); the PDF exports from the **cached** `build_id` (no rebuild) and opens. Confirm in the browser (`npm run dev`, `/build`): briefing preview has **no inline figures/citation markers**, gallery scrolls + lightbox opens, references show T#/L# distinct, Evidence Audit expands, **Ask page unchanged**.

- [ ] **Step 6: Send the PDF + a screenshot to the user, open the Plan 3 PR**

```bash
git push -u origin HEAD
gh pr create --title "feat: Operative Briefing Bundle — Plan 3 (API + Web surface)" \
  --body "Wires the briefing bundle (Plan 1) + PDF renderer (Plan 2) into POST /api/briefing + /api/briefing/pdf (LRU cache, exported==displayed) and rebuilds Build.tsx as the briefing surface. Generated TS types + drift-guard. /api/build* + Ask untouched."
```

---

## Self-Review (against spec §9, §10, §12)

- **§9 additive `POST /api/briefing` + `/api/briefing/pdf`; `/api/build*` untouched** — Tasks 2–3 append routes; no edits to `build`/`build_pdf`. ✓
- **§9 Pydantic self-serializes; embedded Dossier via field_serializer** — `_briefing_response` uses `model_dump(mode="json")` (the model's `@field_serializer` handles case/dossier). ✓
- **§9 response: kind, build_id, topic, case, briefing, figures, references, dossier, provenance** — `model_dump` carries all; `build_id` injected. ✓
- **§9 LRU `_BRIEFING_CACHE` keyed by schema_version + opts; PDF serves the cached bundle** — Task 2 key includes `BRIEFING_SCHEMA_VERSION`; Task 3 serves the cached object, honest 404 on miss. ✓
- **§9 figures reuse `/api/figure?path=` + `_safe_image_path`** — `_briefing_response` augments via existing `_image_url`/`_safe_image_path`. ✓
- **§10 Build.tsx: header+export, briefing preview, scrollable gallery, references, expandable audit, rehearsal retained** — Task 6 renders all six in order. ✓
- **§10 new components OperativeBriefingView / DecisionAlgorithm / Modalities / Equipment / Gallery / References; DossierView→EvidenceAudit (wrap); lightbox reused** — Task 5 (algorithm/modalities/equipment folded into OperativeBriefingView); Task 6 wraps DossierView in `<details>`. ✓
- **§10 TS types generated from the Pydantic schema; responsive + mobile-legible; Ask unchanged** — Task 1 generator + drift guard; gallery/modalities/equipment use `sm:` classes; Ask untouched. ✓
- **§12 offline deterministic; cached PDF == displayed; TS types match output; importorskip n/a; no xdist** — Task 2–3 fakes/monkeypatch; Task 3 asserts the cached object is rendered; Task 1 drift guard. ✓
- **§11 T#/L# distinct, no markers/figures on the briefing preview** — `splitRefs` groups; `OperativeBriefingView` renders no `<img>`/no `source_refs`. ✓

**Deliberately skipped:** the CLI flag Plan 2 mentioned (task + spec §9/§10 don't ask for it); silent PDF rebuild on cache miss (would break exported==displayed); renaming `DossierView.tsx` (wrap is behavior-equivalent, smaller diff).
