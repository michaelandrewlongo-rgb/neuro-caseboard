# Phase 2c — Phone / Web Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a phone-first web app in front of the existing `engine.query()` seam — a long-running FastAPI server (engine kept warm) serving an installable PWA (Layout A), reached from the user's phone over Tailscale; synthesis default bumped to Vertex `gemini-2.5-pro`.

**Architecture:** A thin `server/` (FastAPI) wraps `engine.query()` unchanged and serves a static `webapp/` PWA. Retrieval + corpus stay local in WSL2; only retrieved excerpts + figure images leave (to Vertex), exactly as today. A one-time Windows `netsh portproxy` rule bridges the WSL2 port to the Tailscale interface.

**Tech Stack:** Python 3, FastAPI + Uvicorn, vanilla HTML/CSS/JS PWA (no framework, no CDN — offline-installable), pytest + FastAPI `TestClient`, existing engine (BGE / reranker / BiomedCLIP / LanceDB / Vertex Gemini).

**Spec:** `docs/superpowers/specs/2026-06-07-neuro-textbook-rag-phase2c-phone-web-layer-design.md`

**Engine seam (do NOT modify `engine/`):**
- `engine.query.query(question, config=None) -> QueryResult`
- `QueryResult(answer: str, citations: list[Citation], figures: list[Figure])`
- `Citation(n, book, chapter, page)` — from `engine/synthesize.py`
- `Figure(source_n, book, chapter, page, image_path, caption)` — from `engine/query.py`
- `get_engine(config=None)` caches a process-global engine (warms the heavy models once).
- `Config.assets_dir` — directory holding rendered figure PNGs (figure `image_path` lives here).

## File structure

```
server/
  __init__.py            # empty package marker
  schemas.py             # Pydantic models + QueryResult->AskResponse mapper
  main.py                # FastAPI app: /ask, /healthz, /figures, static mount, warm-on-start
webapp/
  index.html             # Layout A single-page shell + PWA head tags + disclaimer
  styles.css             # phone-first styles
  app.js                 # ask -> render; history (localStorage); copy/share; figure full-screen
  manifest.webmanifest   # installable PWA metadata
  sw.js                  # service worker: cache app shell
  icons/                 # icon-192.png, icon-512.png, apple-touch-icon.png (generated)
scripts/
  serve.sh               # launch uvicorn
  setup-wsl-bridge.ps1   # one-time Windows portproxy + firewall
  make_icons.py          # generate the three PNG icons
tests/
  test_server.py         # API contract tests (engine.query mocked)
engine/config.py         # MODIFY: default VERTEX_MODEL -> gemini-2.5-pro
requirements.txt         # MODIFY: add fastapi, uvicorn, httpx, pillow
README.md                # MODIFY: roadmap Phase 2c -> implemented
```

---

### Task 1: Dependencies + synthesis default bump to `gemini-2.5-pro`

**Files:**
- Modify: `requirements.txt`
- Modify: `engine/config.py:20` (the `VERTEX_MODEL` default in `DEFAULTS`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Add the failing default-model test**

Append to `tests/test_config.py`:

```python
def test_default_vertex_model_is_pro():
    from engine.config import load_config
    cfg = load_config(env_file="does-not-exist.env")
    assert cfg.vertex_model == "gemini-2.5-pro"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_config.py::test_default_vertex_model_is_pro -v`
Expected: FAIL — `assert 'gemini-2.5-flash' == 'gemini-2.5-pro'`

- [ ] **Step 3: Bump the default**

In `engine/config.py`, change the `DEFAULTS` entry:

```python
    "VERTEX_MODEL": "gemini-2.5-pro",
```

- [ ] **Step 4: Run the config tests**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS. (If a pre-existing test asserted `gemini-2.5-flash`, update it to `gemini-2.5-pro` — grep first: `grep -rn "gemini-2.5-flash" tests/`.)

- [ ] **Step 5: Add web dependencies**

Append to `requirements.txt`:

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
pillow>=10.0
```

- [ ] **Step 6: Install**

Run: `python3 -m pip install -r requirements.txt`
Expected: fastapi, uvicorn, httpx, pillow installed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt engine/config.py tests/test_config.py
git commit -m "feat: default synthesis to vertex gemini-2.5-pro; add web deps"
```

---

### Task 2: Response schemas + `QueryResult` -> `AskResponse` mapper

**Files:**
- Create: `server/__init__.py` (empty)
- Create: `server/schemas.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing mapper test**

Create `tests/test_server.py`:

```python
from engine.query import QueryResult, Figure
from engine.synthesize import Citation


def test_to_response_maps_fields_and_builds_figure_url():
    from server.schemas import to_response
    result = QueryResult(
        answer="Give nimodipine 60 mg q4h [1].",
        citations=[Citation(n=1, book="Greenberg", chapter="SAH", page=1290)],
        figures=[Figure(source_n=1, book="Rhoton", chapter="", page=212,
                        image_path="/home/u/assets/figures/rhoton_p212.png",
                        caption="Circle of Willis")],
    )
    resp = to_response(result)
    assert resp.answer == "Give nimodipine 60 mg q4h [1]."
    assert resp.citations[0].model_dump() == {
        "n": 1, "book": "Greenberg", "chapter": "SAH", "page": 1290}
    fig = resp.figures[0]
    assert fig.model_dump() == {
        "source_n": 1, "book": "Rhoton", "page": 212,
        "caption": "Circle of Willis", "url": "/figures/rhoton_p212.png"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_server.py::test_to_response_maps_fields_and_builds_figure_url -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Create the package marker**

Create `server/__init__.py` (empty file).

- [ ] **Step 4: Implement the schemas + mapper**

Create `server/schemas.py`:

```python
from pathlib import Path

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    n: int
    book: str
    chapter: str
    page: int


class FigureOut(BaseModel):
    source_n: int
    book: str
    page: int
    caption: str
    url: str


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut] = []
    figures: list[FigureOut] = []


def to_response(result) -> AskResponse:
    """Map an engine QueryResult to the wire schema. Figure image_path (a local
    absolute path) becomes a /figures/<filename> URL the phone can fetch."""
    return AskResponse(
        answer=result.answer,
        citations=[CitationOut(n=c.n, book=c.book, chapter=c.chapter, page=c.page)
                   for c in result.citations],
        figures=[FigureOut(source_n=f.source_n, book=f.book, page=f.page,
                           caption=f.caption, url=f"/figures/{Path(f.image_path).name}")
                 for f in result.figures],
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/__init__.py server/schemas.py tests/test_server.py
git commit -m "feat: server schemas + QueryResult->AskResponse mapper"
```

---

### Task 3: FastAPI app — `/ask`, `/healthz`, warm-on-start

**Files:**
- Create: `server/main.py`
- Test: `tests/test_server.py` (append)

- [ ] **Step 1: Write the failing API tests**

Append to `tests/test_server.py`:

```python
def _client(monkeypatch, result):
    """A TestClient whose engine is faked (no model load) and whose query seam
    returns `result`. Used as a context manager so the lifespan warm runs."""
    import server.main as m
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    monkeypatch.setattr(m, "engine_query", lambda q, config=None: result)
    return TestClient(m.app)


def test_ask_returns_schema(monkeypatch):
    result = QueryResult(
        answer="Give nimodipine 60 mg q4h [1].",
        citations=[Citation(n=1, book="Greenberg", chapter="SAH", page=1290)],
        figures=[Figure(source_n=1, book="Rhoton", chapter="", page=212,
                        image_path="/x/assets/figures/rhoton_p212.png",
                        caption="Circle of Willis")],
    )
    with _client(monkeypatch, result) as client:
        r = client.post("/ask", json={"question": "nimodipine dosing?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("Give nimodipine")
    assert body["citations"][0]["page"] == 1290
    assert body["figures"][0]["url"] == "/figures/rhoton_p212.png"


def test_ask_refusal_passthrough(monkeypatch):
    result = QueryResult(answer="Not found in the provided sources.",
                         citations=[], figures=[])
    with _client(monkeypatch, result) as client:
        r = client.post("/ask", json={"question": "today's weather?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Not found in the provided sources."
    assert r.json()["figures"] == []


def test_healthz_warm(monkeypatch):
    with _client(monkeypatch, QueryResult(answer="x")) as client:
        assert client.get("/healthz").json() == {"warm": True}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_server.py -k "ask or healthz" -v`
Expected: FAIL — `No module named 'server.main'`

- [ ] **Step 3: Implement the app**

Create `server/main.py`:

```python
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
        _state["warm"] = False
    yield


app = FastAPI(title="Neuro Textbook RAG", lifespan=lifespan)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    return to_response(engine_query(req.question, CONFIG))


@app.get("/healthz")
def healthz():
    return {"warm": _state["warm"]}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: PASS (all three new tests + the mapper test).

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_server.py
git commit -m "feat: FastAPI /ask + /healthz with warm-on-start"
```

---

### Task 4: Figure serving — `GET /figures/{name}` with traversal guard

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_server.py` (append)

- [ ] **Step 1: Write the failing figure-serving tests**

Append to `tests/test_server.py`:

```python
def test_figures_served_and_guarded(monkeypatch, tmp_path):
    import server.main as m
    from fastapi.testclient import TestClient
    png = tmp_path / "rhoton_p212.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    monkeypatch.setattr(m.CONFIG, "assets_dir", tmp_path)
    with TestClient(m.app) as client:
        ok = client.get("/figures/rhoton_p212.png")
        assert ok.status_code == 200
        assert ok.content == b"\x89PNG\r\n\x1a\nFAKE"
        assert client.get("/figures/missing.png").status_code == 404
        # path traversal must not escape assets_dir
        assert client.get("/figures/..%2f..%2fsecret.txt").status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_server.py::test_figures_served_and_guarded -v`
Expected: FAIL — 404 on the valid file (route not defined yet).

- [ ] **Step 3: Add the route**

In `server/main.py`, add the import line and the route (place the route above any future static mount):

```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
```

```python
@app.get("/figures/{name}")
def figure(name: str):
    safe = Path(name).name           # strip any directory component
    path = Path(CONFIG.assets_dir) / safe
    if safe != name or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_server.py
git commit -m "feat: serve figure PNGs at /figures with traversal guard"
```

---

### Task 5: PWA front-end (Layout A) + static mount

**Design constraints (per the user's anti-slop preference):** clean, editorial, calm. Deep slate/ink palette, generous whitespace, a real text typeface (system UI stack is fine). NO purple gradients, glassmorphism, neon, or bento grids. Big tap targets, one-handed reach, readable at arm's length.

**Files:**
- Create: `webapp/index.html`, `webapp/styles.css`, `webapp/app.js`, `webapp/manifest.webmanifest`, `webapp/sw.js`
- Create: `scripts/make_icons.py` → generates `webapp/icons/{icon-192,icon-512,apple-touch-icon}.png`
- Modify: `server/main.py` (append static mount at `/`)
- Test: `tests/test_server.py` (append)

- [ ] **Step 1: Write the failing "shell is served" test**

Append to `tests/test_server.py`:

```python
def test_pwa_shell_and_assets_served(monkeypatch):
    import server.main as m
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    with TestClient(m.app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert 'id="ask-form"' in root.text
        assert client.get("/manifest.webmanifest").status_code == 200
        assert client.get("/sw.js").status_code == 200
        assert client.get("/app.js").status_code == 200
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_server.py::test_pwa_shell_and_assets_served -v`
Expected: FAIL — 404 (no static mount / no files yet).

- [ ] **Step 3: Create `webapp/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Neuro Textbook RAG</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="stylesheet" href="/styles.css">
  <meta name="theme-color" content="#0f172a">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Neuro RAG">
  <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
</head>
<body>
  <header class="topbar">
    <h1>Neuro Textbook RAG</h1>
    <button id="history-toggle" class="iconbtn" aria-label="History">Recent</button>
  </header>

  <form id="ask-form" autocomplete="off">
    <input id="q" name="q" type="text" inputmode="search"
           placeholder="Ask a clinical or anatomy question" enterkeyhint="search">
    <button id="ask-btn" type="submit" aria-label="Ask">Ask</button>
  </form>

  <section id="history" class="history hidden" aria-label="Recent questions"></section>

  <main id="result" class="result" aria-live="polite"></main>

  <p class="disclaimer">Decision-support only · not a clinical order</p>

  <div id="lightbox" class="lightbox hidden" role="dialog" aria-modal="true">
    <img id="lightbox-img" alt="">
  </div>

  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create `webapp/styles.css`**

```css
:root{
  --ink:#0f172a; --paper:#ffffff; --muted:#6b7280; --line:#e6e8ec;
  --accent:#1d4ed8; --accent-soft:#eef2ff; --bg:#f5f6f8;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.55;-webkit-text-size-adjust:100%}
.topbar{display:flex;align-items:center;justify-content:space-between;
  padding:14px 16px env(safe-area-inset-top);background:var(--ink);color:#e2e8f0}
.topbar h1{font-size:16px;font-weight:600;margin:0;letter-spacing:.2px}
.iconbtn{background:transparent;border:1px solid #334155;color:#cbd5e1;
  border-radius:16px;padding:6px 12px;font-size:13px}
#ask-form{display:flex;gap:8px;padding:12px 14px;position:sticky;top:0;
  background:var(--bg);border-bottom:1px solid var(--line);z-index:5}
#q{flex:1;border:1px solid #d6dae0;border-radius:22px;padding:12px 16px;
  font-size:16px;background:var(--paper)}
#ask-btn{border:none;background:var(--accent);color:#fff;border-radius:22px;
  padding:0 20px;font-size:15px;font-weight:600}
#ask-btn:disabled{opacity:.5}
.result{padding:16px 16px 8px;max-width:720px;margin:0 auto}
.answer{font-size:16px}
.answer .cite{color:var(--accent);font-weight:600;cursor:pointer;
  background:var(--accent-soft);border-radius:5px;padding:0 4px;font-size:13px}
.section-h{font-size:11px;text-transform:uppercase;letter-spacing:.6px;
  color:var(--muted);font-weight:700;margin:22px 0 8px}
.fig{margin:0 0 14px}
.fig img{width:100%;border-radius:10px;border:1px solid var(--line);display:block}
.fig figcaption{font-size:12px;color:var(--muted);margin-top:5px}
.src{font-size:13px;color:#374151;padding:8px 0;border-top:1px solid var(--line)}
.toolbar{display:flex;gap:8px;margin:14px 0}
.toolbar button{border:1px solid var(--line);background:var(--paper);
  border-radius:18px;padding:8px 14px;font-size:13px;color:#374151}
.spinner{display:inline-block;width:18px;height:18px;border:2px solid var(--line);
  border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;
  vertical-align:middle;margin-right:8px}
@keyframes spin{to{transform:rotate(360deg)}}
.status{color:var(--muted);padding:8px 0}
.error{color:#b91c1c}
.history{padding:6px 16px 0;max-width:720px;margin:0 auto}
.history button{display:block;width:100%;text-align:left;background:var(--paper);
  border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:6px;
  font-size:14px;color:#374151}
.hidden{display:none}
.disclaimer{text-align:center;color:#9aa3af;font-size:11px;padding:10px 16px 28px}
.lightbox{position:fixed;inset:0;background:rgba(2,6,23,.92);display:flex;
  align-items:center;justify-content:center;padding:16px;z-index:50}
.lightbox img{max-width:100%;max-height:100%;border-radius:8px}
```

- [ ] **Step 5: Create `webapp/app.js`**

```javascript
const HISTORY_KEY = "neuro-rag-history";
const form = document.getElementById("ask-form");
const qInput = document.getElementById("q");
const askBtn = document.getElementById("ask-btn");
const resultEl = document.getElementById("result");
const historyEl = document.getElementById("history");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");

function escapeHtml(s){
  return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

// Minimal markdown: bold, headings, and bullet lines. Then citation chips.
function renderAnswer(text){
  const lines = escapeHtml(text).split("\n");
  let html = "", inList = false;
  for(const line of lines){
    const b = line.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    if(/^\s*[-*]\s+/.test(line)){
      if(!inList){ html += "<ul>"; inList = true; }
      html += "<li>" + b.replace(/^\s*[-*]\s+/, "") + "</li>";
    } else {
      if(inList){ html += "</ul>"; inList = false; }
      if(/^#{1,3}\s/.test(line)) html += "<h3>" + b.replace(/^#{1,3}\s/, "") + "</h3>";
      else if(line.trim() === "") html += "";
      else html += "<p>" + b + "</p>";
    }
  }
  if(inList) html += "</ul>";
  // [n] citation chips that scroll to the source row
  return html.replace(/\[(\d+)\]/g,
    '<span class="cite" onclick="scrollToSource($1)">[$1]</span>');
}

window.scrollToSource = function(n){
  const el = document.getElementById("src-" + n);
  if(el) el.scrollIntoView({behavior:"smooth", block:"center"});
};

function plainTextForCopy(question, data){
  let out = "Q: " + question + "\n\n" + data.answer + "\n\nSources:\n";
  data.citations.forEach(c => {
    out += `[${c.n}] ${c.book}${c.chapter ? ", " + c.chapter : ""}, p.${c.page}\n`;
  });
  return out;
}

function render(question, data){
  let html = '<div class="answer">' + renderAnswer(data.answer) + "</div>";
  html += '<div class="toolbar"><button id="copy-btn">Copy</button>';
  if(navigator.share) html += '<button id="share-btn">Share</button>';
  html += "</div>";
  if(data.figures && data.figures.length){
    html += '<div class="section-h">Figures</div>';
    data.figures.forEach(f => {
      html += `<figure class="fig"><img src="${f.url}" alt="${escapeHtml(f.caption)}" `
        + `onclick="openFig('${f.url}')"><figcaption>[${f.source_n}] `
        + `${escapeHtml(f.book)}, p.${f.page} — ${escapeHtml(f.caption)}</figcaption></figure>`;
    });
  }
  if(data.citations && data.citations.length){
    html += '<div class="section-h">Sources</div>';
    data.citations.forEach(c => {
      html += `<div class="src" id="src-${c.n}">[${c.n}] ${escapeHtml(c.book)}`
        + `${c.chapter ? ", " + escapeHtml(c.chapter) : ""}, p.${c.page}</div>`;
    });
  }
  resultEl.innerHTML = html;
  const copyBtn = document.getElementById("copy-btn");
  copyBtn.onclick = () => navigator.clipboard.writeText(plainTextForCopy(question, data))
    .then(() => { copyBtn.textContent = "Copied"; });
  const shareBtn = document.getElementById("share-btn");
  if(shareBtn) shareBtn.onclick = () =>
    navigator.share({title:"Neuro RAG", text:plainTextForCopy(question, data)});
}

window.openFig = function(url){
  lightboxImg.src = url; lightbox.classList.remove("hidden");
};
lightbox.onclick = () => lightbox.classList.add("hidden");

function loadHistory(){ try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
  catch { return []; } }
function saveHistory(list){ localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 20))); }
function pushHistory(question){
  const list = loadHistory().filter(q => q !== question);
  list.unshift(question); saveHistory(list); renderHistory();
}
function renderHistory(){
  const list = loadHistory();
  historyEl.innerHTML = list.map(q =>
    `<button>${escapeHtml(q)}</button>`).join("");
  [...historyEl.querySelectorAll("button")].forEach((b, i) => {
    b.onclick = () => { qInput.value = list[i]; historyEl.classList.add("hidden"); ask(list[i]); };
  });
}
document.getElementById("history-toggle").onclick = () => {
  renderHistory(); historyEl.classList.toggle("hidden");
};

async function ask(question){
  askBtn.disabled = true;
  resultEl.innerHTML = '<div class="status"><span class="spinner"></span>Searching textbooks…</div>';
  try {
    const r = await fetch("/ask", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({question})});
    if(!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    render(question, data);
    pushHistory(question);
  } catch(e){
    resultEl.innerHTML = '<div class="status error">Can’t reach the textbook server — is your '
      + 'workstation awake and Tailscale connected? <button onclick="ask(' 
      + JSON.stringify(question) + ')">Retry</button></div>';
  } finally {
    askBtn.disabled = false;
  }
}
window.ask = ask;

form.onsubmit = (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  if(q) ask(q);
};

if("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
```

- [ ] **Step 6: Create `webapp/manifest.webmanifest`**

```json
{
  "name": "Neuro Textbook RAG",
  "short_name": "Neuro RAG",
  "start_url": ".",
  "scope": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#0f172a",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
```

- [ ] **Step 7: Create `webapp/sw.js`**

```javascript
const CACHE = "neuro-rag-v1";
const SHELL = ["/", "/index.html", "/styles.css", "/app.js",
  "/manifest.webmanifest", "/icons/icon-192.png", "/icons/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache answers or figure images — always go to the network.
  if(url.pathname.startsWith("/ask") || url.pathname.startsWith("/figures")) return;
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
```

- [ ] **Step 8: Create `scripts/make_icons.py` and generate the icons**

```python
"""Generate the PWA icons (no design dependency — a simple ink tile with 'N')."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "webapp" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
INK = (15, 23, 42)        # #0f172a
PAPER = (226, 232, 240)   # #e2e8f0


def make(size, name):
    img = Image.new("RGB", (size, size), INK)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.56))
    except OSError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2), "N", fill=PAPER, font=font, anchor="mm")
    img.save(OUT / name)


for size, name in [(192, "icon-192.png"), (512, "icon-512.png"),
                   (180, "apple-touch-icon.png")]:
    make(size, name)
print("icons written to", OUT)
```

Run: `python3 scripts/make_icons.py`
Expected: `icons written to .../webapp/icons` and three PNGs present.

- [ ] **Step 9: Mount the static app (append to `server/main.py`)**

Add the import and, **as the last line of the file** (so API routes take precedence), the mount:

```python
from fastapi.staticfiles import StaticFiles
```

```python
# Static PWA at root — MUST be mounted last so /ask, /healthz, /figures win.
app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
```

- [ ] **Step 10: Run the full server test suite**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: PASS — including `test_pwa_shell_and_assets_served`.

- [ ] **Step 11: Commit**

```bash
git add webapp/ scripts/make_icons.py server/main.py tests/test_server.py
git commit -m "feat: phone-first PWA (Layout A) + static mount + icons"
```

---

### Task 6: Launch + WSL2↔Tailscale bridge scripts

**Files:**
- Create: `scripts/serve.sh`
- Create: `scripts/setup-wsl-bridge.ps1`

- [ ] **Step 1: Create `scripts/serve.sh`**

```bash
#!/usr/bin/env bash
# Launch the warm, long-running server. Run from the repo root inside WSL2.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
echo "Serving on 0.0.0.0:${PORT} (WSL2). Reach it from the phone via the Windows Tailscale IP."
exec python3 -m uvicorn server.main:app --host 0.0.0.0 --port "${PORT}"
```

Run: `chmod +x scripts/serve.sh`

- [ ] **Step 2: Create `scripts/setup-wsl-bridge.ps1`**

```powershell
# Run ONCE in an elevated (Admin) Windows PowerShell. Forwards the Windows port
# (reachable on the Tailscale interface) to the WSL2 server, and opens the firewall.
param([int]$Port = 8000)

$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
if (-not $wslIp) { Write-Error "Could not determine WSL2 IP (is WSL running?)"; exit 1 }
Write-Host "WSL2 IP: $wslIp  Port: $Port"

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Port `
  connectaddress=$wslIp connectport=$Port

New-NetFirewallRule -DisplayName "Neuro RAG $Port" -Direction Inbound `
  -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction SilentlyContinue | Out-Null

Write-Host "Done. From your phone (on Tailscale) open: http://<this-PC-tailscale-ip>:$Port"
Write-Host "NOTE: the WSL2 IP changes on reboot — re-run this script if the phone can't connect."
```

- [ ] **Step 3: Commit**

```bash
git add scripts/serve.sh scripts/setup-wsl-bridge.ps1
git commit -m "feat: serve.sh launcher + Windows WSL2<->Tailscale bridge script"
```

---

### Task 7: Provider-switch validation, manual e2e, docs

**Files:**
- Modify: `README.md` (roadmap + a "Phase 2c — phone/web app" usage section)

- [ ] **Step 1: Confirm the whole suite is green**

Run: `python3 -m pytest -q`
Expected: all tests pass (the prior 37 + the new `test_server.py` set). No `engine/` test changed.

- [ ] **Step 2: Provider-switch validation (needs Vertex auth)**

Ensure `.env` has `SYNTH_PROVIDER=vertex`, `VERTEX_MODEL=gemini-2.5-pro`, `GOOGLE_CLOUD_PROJECT=<project>`, then `gcloud auth application-default login`. Run a few in-domain queries through the CLI (same warm engine path):

```bash
python3 -m cli.ask "Nimodipine dosing and duration for aneurysmal SAH?"
python3 -m cli.ask "Adult atlanto-dental interval threshold suggesting instability?"
python3 -m cli.ask "What is the capital of France?"   # must refuse: off-domain
```

Expected: the two clinical answers are correct, every claim carries a `[n]` citation, and the off-domain query returns *"Not found in the provided sources."* Record the outcomes. If any clinical answer is wrong or uncited, STOP and investigate before shipping (do not just retune the question).

- [ ] **Step 3: Manual end-to-end on the phone**

1. WSL2: `./scripts/serve.sh` (wait for "Application startup complete").
2. Windows (Admin PowerShell): `./scripts/setup-wsl-bridge.ps1`.
3. Phone (on Tailscale): open `http://<PC-tailscale-ip>:8000`, ask a question.
4. Verify: answer renders (Layout A), `[n]` chips scroll to sources, a figure opens full-screen on tap, Copy works, Recent shows the question and re-runs it.
5. iOS Safari → Share → **Add to Home Screen**; open the icon; confirm it launches full-screen.

- [ ] **Step 4: Update the README roadmap**

In `README.md`, change the Phase 2c bullet from "deferred" to implemented, and add a short usage section:

```markdown
- **Phase 2c — phone/web layer: implemented.** A FastAPI server (`server/main.py`)
  wraps `engine.query` and serves an installable phone-first PWA (`webapp/`, Layout A).
  Retrieval + corpus stay local in WSL2; synthesis runs on Vertex `gemini-2.5-pro`.
  Launch with `scripts/serve.sh`; reach it from the phone over Tailscale after a one-time
  `scripts/setup-wsl-bridge.ps1` on the Windows host.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: mark Phase 2c implemented; phone/web app usage"
```

---

## Self-review (completed during planning)

- **Spec coverage:** local retrieval / Vertex `gemini-2.5-pro` default (Task 1) · long-running warm server (Task 3 lifespan) · `/ask` 1:1 `QueryResult` mapping (Tasks 2–3) · `/figures` (Task 4) · `/healthz` warming state (Task 3) · Layout A + history + copy/share + PWA install (Task 5) · screen states incl. refusal passthrough & error (Tasks 3, 5) · Tailscale/WSL2 bridge (Task 6) · provider validation + tests + data-boundary note + README (Task 7). No spec requirement left without a task.
- **No placeholders:** every code/test/script step contains complete content; no "TBD"/"add error handling".
- **Type consistency:** `engine_query`, `get_engine`, `to_response`, `AskRequest/AskResponse/CitationOut/FigureOut`, `CONFIG.assets_dir`, and the `Figure`/`Citation` field names are used identically across tasks and match the real engine signatures.
- **Out of scope (unchanged):** streaming, voice, app passcode, cloud-hosted engine — none added.
