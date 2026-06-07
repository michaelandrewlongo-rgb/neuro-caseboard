# Local Answer Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve a minimal localhost webpage that shows `cli.ask` answers — the text, the figure images, and the sources — over the existing `/ask` and `/figures` endpoints.

**Architecture:** Keep `server/main.py` and its endpoints unchanged except for one line: point the static mount at a new dependency-free `web/` page instead of the `webapp/` PWA. The page POSTs a question to `/ask` and renders `answer` (plain text, with clickable `[n]`), `figures` (images), and `citations` (sources). The old PWA front end is archived, not deleted.

**Tech Stack:** FastAPI (existing), Starlette `StaticFiles`, vanilla HTML/CSS/JS (no framework, no CDN), pytest + `fastapi.testclient`.

**Branch:** `feat/local-viewer` (already created; pre-existing WIP preserved at `23a918e`, spec at `8746c19`).

**Spec:** `docs/superpowers/specs/2026-06-07-local-answer-viewer-design.md`

---

## File Structure

- **Create** `web/index.html` — the page shell + inline CSS. Owns layout/styling; one input form (`id="ask-form"`), one results container (`id="result"`).
- **Create** `web/app.js` — fetch `/ask`, render answer/figures/sources, loading + error states. No history, no service worker, no markdown.
- **Modify** `server/main.py:84-86` — change the static mount from `webapp/` to `web/`.
- **Modify** `tests/test_server.py:148-159` — replace the PWA-shell test with a minimal-page test.
- **Modify** `scripts/serve.sh:6` — change the phone/Tailscale launch message to a localhost message.
- **Move** `webapp/` → `archive/webapp/` (via `git mv`, preserving history).

The `/ask`, `/figures`, `/healthz` endpoints, `server/schemas.py`, `server/auth.py`, and the passcode middleware are **unchanged**. The middleware is inert locally (no `APP_PASSCODE` in `.env`).

---

## Task 1: Create the minimal page (`web/index.html`, `web/app.js`)

**Files:**
- Create: `web/index.html`
- Create: `web/app.js`

This task creates static assets only; it is verified end-to-end by the server test in Task 2 and the manual gate in Task 4 (the repo has no JS test harness, so there is no unit test here).

- [ ] **Step 1: Create `web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Neuro Textbook RAG</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2rem 1rem 4rem;
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1a1a1a; background: #fafafa;
  }
  main { max-width: 760px; margin: 0 auto; }
  h1 { font-size: 1.15rem; font-weight: 600; margin: 0 0 1.25rem; color: #333; }
  form { display: flex; gap: .5rem; margin-bottom: 1.5rem; }
  #q {
    flex: 1; padding: .65rem .8rem; font-size: 1rem;
    border: 1px solid #ccc; border-radius: 6px; background: #fff;
  }
  #q:focus { outline: 2px solid #2f6f9f; border-color: #2f6f9f; }
  #ask-btn {
    padding: .65rem 1.1rem; font-size: 1rem; cursor: pointer;
    border: 1px solid #2f6f9f; border-radius: 6px; background: #2f6f9f; color: #fff;
  }
  #ask-btn:disabled { opacity: .6; cursor: default; }
  .status { color: #666; padding: 1rem 0; }
  .status.error { color: #a12; }
  .answer { white-space: pre-wrap; }
  .answer .cite { color: #2f6f9f; font-weight: 600; text-decoration: none; }
  .answer .cite:hover { text-decoration: underline; }
  .section-h {
    margin: 2rem 0 .75rem; font-size: .8rem; letter-spacing: .06em;
    text-transform: uppercase; color: #888;
    border-bottom: 1px solid #e3e3e3; padding-bottom: .3rem;
  }
  figure { margin: 0 0 1.5rem; }
  figure img {
    max-width: 100%; height: auto;
    border: 1px solid #ddd; border-radius: 6px; background: #fff;
  }
  figcaption { font-size: .85rem; color: #666; margin-top: .4rem; }
  .src { padding: .35rem 0; font-size: .92rem; }
  .src:target { background: #fff6d6; }
</style>
</head>
<body>
<main>
  <h1>Neuro Textbook RAG</h1>
  <form id="ask-form">
    <input id="q" type="text" placeholder="Ask a neurosurgery question…" autocomplete="off" autofocus>
    <button id="ask-btn" type="submit">Ask</button>
  </form>
  <div id="result"></div>
</main>
<script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `web/app.js`**

```javascript
const form = document.getElementById("ask-form");
const qInput = document.getElementById("q");
const askBtn = document.getElementById("ask-btn");
const resultEl = document.getElementById("result");

function escapeHtml(s){
  return String(s).replace(/[&<>"]/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

// Plain text: escape, preserve line breaks (CSS white-space:pre-wrap), and turn
// [n] markers into links that jump to source n. Markdown/LaTeX is deferred.
function renderAnswer(text){
  return escapeHtml(text).replace(/\[(\d+)\]/g,
    '<a class="cite" href="#src-$1">[$1]</a>');
}

function render(data){
  let html = '<div class="answer">' + renderAnswer(data.answer || "") + "</div>";

  if(data.figures && data.figures.length){
    html += '<div class="section-h">Figures</div>';
    data.figures.forEach(f => {
      const cap = f.caption ? escapeHtml(f.caption) : `${escapeHtml(f.book)}, p.${f.page}`;
      html += `<figure><img src="${escapeHtml(f.url)}" alt="${cap}" loading="lazy">`
        + `<figcaption>Source [${f.source_n}] — ${escapeHtml(f.book)}, p.${f.page}`
        + (f.caption ? " — " + escapeHtml(f.caption) : "")
        + `</figcaption></figure>`;
    });
  }

  if(data.citations && data.citations.length){
    html += '<div class="section-h">Sources</div>';
    data.citations.forEach(c => {
      html += `<div class="src" id="src-${c.n}">[${c.n}] ${escapeHtml(c.book)}`
        + (c.chapter ? ", " + escapeHtml(c.chapter) : "")
        + `, p.${c.page}</div>`;
    });
  }
  resultEl.innerHTML = html;
}

async function ask(question){
  askBtn.disabled = true;
  askBtn.textContent = "Searching…";
  resultEl.innerHTML = '<div class="status">Searching textbooks…</div>';
  try {
    const r = await fetch("/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question}),
    });
    if(!r.ok) throw new Error("HTTP " + r.status);
    render(await r.json());
  } catch(e){
    resultEl.innerHTML = '<div class="status error">Couldn\'t reach the textbook server — '
      + 'is it running? (' + escapeHtml(e.message) + ')</div>';
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask";
  }
}

form.onsubmit = (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  if(q) ask(q);
};
```

- [ ] **Step 3: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: minimal local answer viewer page (web/)"
```

---

## Task 2: Point the server mount at `web/` (TDD)

**Files:**
- Modify: `tests/test_server.py:148-159` (replace `test_pwa_shell_and_assets_served`)
- Modify: `server/main.py:84-86`

- [ ] **Step 1: Replace the PWA-shell test with a minimal-page test**

In `tests/test_server.py`, delete the whole `test_pwa_shell_and_assets_served` function (lines 148-159) and replace it with:

```python
def test_minimal_page_served(monkeypatch):
    import server.main as m
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    monkeypatch.setattr(m.CONFIG, "app_passcode", "")
    with TestClient(m.app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert 'id="ask-form"' in root.text
        assert client.get("/app.js").status_code == 200
        # The PWA shell is archived: no service worker, no manifest.
        assert client.get("/sw.js").status_code == 404
        assert client.get("/manifest.webmanifest").status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/neuro-textbook-rag && python3 -m pytest tests/test_server.py::test_minimal_page_served -v`
Expected: FAIL — the mount still serves `webapp/`, which contains `sw.js`, so `GET /sw.js` returns `200`, not the asserted `404`.

- [ ] **Step 3: Change the static mount to `web/`**

In `server/main.py`, replace the final block (lines 84-86):

```python
# Static PWA at root — MUST be mounted last so /ask, /healthz, /figures win.
_WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
app.mount("/", StaticFiles(directory=_WEBAPP_DIR, html=True), name="webapp")
```

with:

```python
# Minimal local viewer at root — MUST be mounted last so /ask, /healthz, /figures win.
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/neuro-textbook-rag && python3 -m pytest tests/test_server.py -v`
Expected: PASS — `web/` has `index.html` (contains `id="ask-form"`) and `app.js` (200), and has no `sw.js`/`manifest.webmanifest` (404). All other `test_server.py` tests still pass (their endpoints are unchanged).

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_server.py
git commit -m "feat: serve minimal web/ page at root instead of the PWA shell"
```

---

## Task 3: Archive the PWA front end and fix the launch message

**Files:**
- Move: `webapp/` → `archive/webapp/`
- Modify: `scripts/serve.sh:6`

- [ ] **Step 1: Move the PWA front end into archive/**

```bash
cd ~/neuro-textbook-rag && mkdir -p archive && git mv webapp archive/webapp
```

This moves the PWA shell, `app.js`, `styles.css` (dark theme), `sw.js` (service-worker kill-switch), `manifest.webmanifest`, and `icons/` together. Nothing in `server/`, `tests/`, or `scripts/serve.sh` references `webapp/` after Task 2.

- [ ] **Step 2: Update the launch message in `scripts/serve.sh`**

Replace line 6:

```bash
echo "Serving on 0.0.0.0:${PORT} (WSL2). Reach it from the phone via the Windows Tailscale IP."
```

with:

```bash
echo "Serving on http://localhost:${PORT}  — open it in your browser (Ctrl-C to stop)."
```

- [ ] **Step 3: Run the full test suite to verify nothing broke**

Run: `cd ~/neuro-textbook-rag && python3 -m pytest -q`
Expected: PASS — the same count as before this plan, minus zero (the renamed server test still counts as one). No test references `webapp/`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: archive PWA front end to archive/webapp; localhost launch message"
```

---

## Task 4: Manual verification gate

This is a human (or operator) step — there is no automated browser test in this repo.

- [ ] **Step 1: Start the server**

```bash
cd ~/neuro-textbook-rag && ./scripts/serve.sh
```
Expected: prints `Serving on http://localhost:8000 …`, then uvicorn startup. The engine warms once on boot (BGE models load — tens of seconds); wait for `Application startup complete`.

- [ ] **Step 2: Open the page**

Open `http://localhost:8000` in a desktop browser. Expected: the "Neuro Textbook RAG" heading, a question box, and an "Ask" button. No login.

- [ ] **Step 3: Run a real query**

Type an in-domain question (e.g. *"What are the segments of the internal carotid artery?"*) and click Ask. Expected (first query may take ~15-20 s on GPU):
- the answer text renders with `[n]` markers shown as blue links;
- clicking an `[n]` link jumps to and highlights that source under "Sources";
- a "Figures" section shows the figure image(s) with captions;
- a "Sources" section lists `[n] Book — Chapter, p.X`.

- [ ] **Step 4: Confirm the off-domain refusal still surfaces cleanly**

Ask something off-domain (e.g. *"What's the weather today?"*). Expected: the answer renders the "Not found in the provided sources." refusal with no figures and no sources — no error state.

---

## Self-Review

**Spec coverage:**
- Localhost page, type → answer/figures/sources → Tasks 1, 2, 4. ✓
- Answer as plain text with clickable `[n]` → `web/app.js` `renderAnswer`. ✓
- Figures as images with caption fallback → `render()` figures block. ✓
- Sources numbered list with `id` anchors → `render()` citations block + `.src:target` CSS. ✓
- Reuse `/ask` + `/figures` unchanged → only the mount line changes. ✓
- Dependency-free / offline-clean → no CDN, no libraries. ✓
- Passcode inert locally → no change; middleware passes through when `APP_PASSCODE` unset. ✓
- Archive (not delete) `webapp/` → Task 3 `git mv`. ✓
- Reversibility/branch safety → done before this plan (`23a918e` checkpoint, `master` untouched). ✓
- Testing: update server test + smoke + manual gate → Tasks 2, 4. ✓
- Non-goals (phone, PWA, SW, tunnel, cloud, login UX, history, markdown) → none added. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete content. ✓

**Type/name consistency:** Element IDs `ask-form`, `q`, `ask-btn`, `result` match between `index.html` and `app.js`; `renderAnswer`/`render`/`ask` defined and called consistently; figure fields (`url`, `caption`, `book`, `page`, `source_n`) and citation fields (`n`, `book`, `chapter`, `page`) match `server/schemas.py`. ✓
