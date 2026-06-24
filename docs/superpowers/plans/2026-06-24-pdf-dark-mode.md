# Dark-Mode / Signal PDF Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the generated HTML→PDF exports (Build dossier + Ask briefing) from the white "Neo Brutalism" identity to the web app's dark "Neurosurgery·Signal" modern layout, switchable between a **dark (screen)** and a **light (print)** surface via the existing `CASEBOARD_PDF_STYLE` env var, and add Chromium to the Docker image so the deployed web app actually renders the HTML path.

**Architecture:** Both HTML→PDF builders (`caseboard_pdf.py` dossier, `briefing_pdf.py` briefing) share one stylesheet, `exec_navy.py::EXEC_NAVY_CSS`. Make that stylesheet **theme-aware**: one modern structural CSS body driven by a `:root` token block chosen at render time (`base_css(theme)`), with two token sets — `SIGNAL` (dark) and `PRINT` (light). Thread a `theme` argument from `pipeline.py` (which reads `CASEBOARD_PDF_STYLE`) through the render/build functions into `base_css`. The fpdf2 offline fallbacks (`render_pdf.py`, `render_briefing_clinical_pdf`) are OUT OF SCOPE and stay brutalist.

**Tech Stack:** Python 3 + pytest; HTML/CSS string templates rendered to PDF by Playwright Chromium (`page.pdf`); fonts DM Sans + Space Mono (already used). Docker multi-stage (python:3.12-slim runtime).

## Global Constraints

- **Match the web `@theme` tokens** (`web/src/index.css`) — SIGNAL (dark): bg `#000000`, panel `#0a0a0a`, ink `#ededed`, muted `#8a8a8a`, border `rgba(255,255,255,.09)`, accent/blue `#6b93ff`, status supported `#34e07f` / verify `#ffc94d` / quar `#ff5a5a`. PRINT (light, ink-friendly, NO gradients): bg `#ffffff`, panel `#fafafa`, ink `#1a1a1a`, muted `#555555`, border `#e5e5e5`, accent/blue `#2a52cc`, status `#1a7f4b` / `#b45309` / `#c8102e`. Both keep modern structure: `--radius:7px`, `--border:1px`, no hard offset shadows, DM Sans + Space Mono, `print-color-adjust:exact`.
- **Back-compat:** `EXEC_NAVY_CSS` must remain an importable module-level name equal to `base_css("signal")` (other modules import it).
- **`CASEBOARD_PDF_STYLE` values:** `signal` (dark, NEW DEFAULT) · `print` (light) · `clinical` (fpdf2 fallback, unchanged). Legacy `exec` → treated as `signal`. fpdf2 fallback still triggers on `clinical` OR when Chromium is unavailable.
- **Every logic change ships with a test** (pytest). Match the substring-assert pattern in `tests/test_exec_navy.py`.
- **Python tests run under:** `cd /home/michael/PROJECTS/neuro-caseboard/.claude/worktrees/pdf-dark-mode/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q <file>` (full suite ~17 min — never invoke it; never pytest-xdist). Scope to single files during the loop.
- **Worktree:** all work happens in `/home/michael/PROJECTS/neuro-caseboard/.claude/worktrees/pdf-dark-mode/.project-loop/wt` on branch `loop/pdf-dark-mode`.
- **No new clinical/string hardcoding;** CSS only. Do not touch the fpdf2 fallbacks.

---

### Task 1: Theme-aware `base_css(theme)` + SIGNAL/PRINT token sets (exec_navy.py)

Replace the single white-brutalist `EXEC_NAVY_CSS` constant with a `base_css(theme)` function: a `:root` token block (chosen by theme) + one modern structural CSS body that references only `var(--…)` tokens. Modernize the structure: `border-radius:0`→`var(--radius)` (7px), `border:2px solid #000`→`var(--border) solid var(--line)`, drop the `box-shadow:3px 3px 0 0 #000` hard offsets, white grounds→`var(--bg)`/`var(--panel)`. Keep `EXEC_NAVY_CSS = base_css("signal")` for importers.

**Files:**
- Modify: `neuro_caseboard/exec_navy.py` (replace the `EXEC_NAVY_CSS` literal at lines 17–112 with `SIGNAL_TOKENS`, `PRINT_TOKENS`, `_STRUCTURE_CSS`, `base_css()`, and `EXEC_NAVY_CSS = base_css("signal")`)
- Test: `tests/test_exec_navy.py` (add theme tests; UPDATE the existing `test_css_carries_the_brand_tokens`)

**Interfaces:**
- Produces: `base_css(theme: str = "signal") -> str` — returns full CSS (`:root{…}` + structure). `theme` in `{"signal","print"}`; any other value (incl. `"exec"`) falls back to `"signal"`.
- Produces: module constant `EXEC_NAVY_CSS: str = base_css("signal")` (unchanged import name).
- `inline()` and `img_data_uri()` are untouched.

- [x] **Step 1: Update + add tests**

In `tests/test_exec_navy.py`, change the import to `from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, base_css, inline, img_data_uri`, REPLACE `test_css_carries_the_brand_tokens` and append theme tests:

```python
def test_css_carries_the_brand_tokens():
    # Signal (dark) is the default identity: blue DTI accent, DM Sans + Space Mono.
    assert "--accent:#6b93ff" in EXEC_NAVY_CSS
    assert "DM+Sans" in EXEC_NAVY_CSS and "Space+Mono" in EXEC_NAVY_CSS
    assert EXEC_NAVY_CSS == base_css("signal")


def test_signal_theme_is_dark():
    css = base_css("signal")
    assert "--bg:#000000" in css and "--ink:#ededed" in css
    assert "--accent:#6b93ff" in css
    assert "--supported:#34e07f" in css and "--verify:#ffc94d" in css and "--quar:#ff5a5a" in css
    assert "--line:rgba(255,255,255,.09)" in css
    # modernized structure (no brutalist square corners / hard offset shadow)
    assert "--radius:7px" in css
    assert "3px 3px 0 0" not in css


def test_print_theme_is_light_and_ink_friendly():
    css = base_css("print")
    assert "--bg:#ffffff" in css and "--ink:#1a1a1a" in css
    assert "--accent:#2a52cc" in css                       # darker -ink blue for contrast on white
    assert "--supported:#1a7f4b" in css and "--verify:#b45309" in css and "--quar:#c8102e" in css
    assert "--line:#e5e5e5" in css
    assert "linear-gradient" not in css                    # no gradients in print (ink-friendly)
    assert "print-color-adjust:exact" in css


def test_unknown_style_falls_back_to_signal():
    assert base_css("exec") == base_css("signal")
    assert base_css("nonsense") == base_css("signal")
```

- [x] **Step 2: Run the tests, verify they fail**

Run: `cd <worktree> && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/test_exec_navy.py`
Expected: FAIL (`base_css` not defined / old `#ff3333` token).

- [x] **Step 3: Implement `base_css` + token sets**

In `neuro_caseboard/exec_navy.py`, replace the `EXEC_NAVY_CSS = """…"""` literal with two `:root` token strings and a structural body that uses only `var(--…)`. Define:

```python
SIGNAL_TOKENS = """:root{
  --bg:#000000; --panel:#0a0a0a; --panel-grad:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.012));
  --ink:#ededed; --muted:#8a8a8a; --faint:#6b6b6b;
  --line:rgba(255,255,255,.09); --line-soft:rgba(255,255,255,.06);
  --accent:#6b93ff; --blue:#6b93ff; --yellow:#ffc94d;
  --supported:#34e07f; --verify:#ffc94d; --quar:#ff5a5a;
  --ui:'DM Sans',system-ui,sans-serif; --read:'DM Sans',system-ui,sans-serif; --mono:'Space Mono',ui-monospace,monospace;
  --radius:7px; --border:1px;
}"""
PRINT_TOKENS = """:root{
  --bg:#ffffff; --panel:#fafafa; --panel-grad:none;
  --ink:#1a1a1a; --muted:#555555; --faint:#777777;
  --line:#e5e5e5; --line-soft:#eeeeee;
  --accent:#2a52cc; --blue:#2a52cc; --yellow:#b45309;
  --supported:#1a7f4b; --verify:#b45309; --quar:#c8102e;
  --ui:'DM Sans',system-ui,sans-serif; --read:'DM Sans',system-ui,sans-serif; --mono:'Space Mono',ui-monospace,monospace;
  --radius:7px; --border:1px;
}"""
```

`_STRUCTURE_CSS` = the existing structural rules with the import-font `@import` line kept, and every hardcoded brutalist value swapped for a token: `background:#ffffff`→`background:var(--bg)`; `.masthead`/`.metric`/panel grounds→`var(--panel)` (+ `background-image:var(--panel-grad)` on panels that had the white gradient); `border:2px solid #000`→`border:var(--border) solid var(--line)`; `box-shadow:3px 3px 0 0 #000`→remove; `border-radius:0`→`border-radius:var(--radius)`; `color:#000`/`var(--ink)` already token; `.eyebrow` brutalist yellow box→`color:var(--accent);border:var(--border) solid var(--line);background:transparent`. Keep `-webkit-print-color-adjust:exact; print-color-adjust:exact` on `html,body`.

```python
def base_css(theme: str = "signal") -> str:
    tokens = PRINT_TOKENS if theme == "print" else SIGNAL_TOKENS
    return tokens + _STRUCTURE_CSS

EXEC_NAVY_CSS = base_css("signal")
```

- [x] **Step 4: Run the tests, verify they pass**

Run: `cd <worktree> && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/test_exec_navy.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add neuro_caseboard/exec_navy.py tests/test_exec_navy.py
git commit -m "feat(pdf): theme-aware base_css with SIGNAL (dark) + PRINT (light) token sets"
```

---

### Task 2: Thread `theme` through the dossier HTML (caseboard_pdf.py)

`build_caseboard_html` currently inlines `EXEC_NAVY_CSS + _CASE_EXTRA_CSS`. Add a `theme` param and inject `base_css(theme)` instead of the constant; soften `_CASE_EXTRA_CSS`'s own borders/shadows/radius to tokens. Pass `theme` from `render_caseboard_pdf`.

**Files:**
- Modify: `neuro_caseboard/caseboard_pdf.py:98` (`build_caseboard_html` signature + CSS join + `_CASE_EXTRA_CSS`), `:178` (`render_caseboard_pdf` signature + call-through)
- Test: `tests/test_caseboard_pdf.py`

**Interfaces:**
- Consumes: `base_css(theme)` from Task 1.
- Produces: `build_caseboard_html(dossier, *, subtitle="", today=None, theme="signal") -> str`; `render_caseboard_pdf(dossier, out_path, *, subtitle="", theme="signal") -> str`.

- [x] **Step 1: Write the failing test**

Append to `tests/test_caseboard_pdf.py` (reuse the module's existing dossier fixture/builder; if it builds a `Dossier` inline, mirror that):

```python
def test_build_caseboard_html_signal_is_dark_print_is_light(_min_dossier):
    dark = build_caseboard_html(_min_dossier, subtitle="X", theme="signal")
    light = build_caseboard_html(_min_dossier, subtitle="X", theme="print")
    assert "--bg:#000000" in dark and "--accent:#6b93ff" in dark
    assert "--bg:#ffffff" in light and "--accent:#2a52cc" in light


def test_build_caseboard_html_defaults_to_signal(_min_dossier):
    assert "--bg:#000000" in build_caseboard_html(_min_dossier, subtitle="X")
```

(If no shared dossier fixture exists, add a module-level `_min_dossier` pytest fixture building the smallest valid `Dossier` — copy the construction already used by the file's other tests.)

- [x] **Step 2: Run the test, verify it fails** — `pytest -q tests/test_caseboard_pdf.py` → FAIL (`theme` unexpected kwarg).

- [x] **Step 3: Implement** — add `theme="signal"` to both signatures; change the CSS join from `EXEC_NAVY_CSS, _CASE_EXTRA_CSS` to `base_css(theme), _CASE_EXTRA_CSS` (import `base_css`); in `render_caseboard_pdf`, pass `theme` into `build_caseboard_html(...)`. Swap any `2px solid #000` / `box-shadow:…#000` / `border-radius:0` inside `_CASE_EXTRA_CSS` for `var(--border) solid var(--line)` / removed / `var(--radius)`.

- [x] **Step 4: Run the test, verify it passes** — `pytest -q tests/test_caseboard_pdf.py` → PASS.

- [x] **Step 5: Commit**

```bash
git add neuro_caseboard/caseboard_pdf.py tests/test_caseboard_pdf.py
git commit -m "feat(pdf): thread theme through the dossier HTML builder"
```

---

### Task 3: Thread `theme` through the briefing HTML (briefing_pdf.py)

Same change for the Ask briefing: `build_briefing_html` injects `base_css(theme) + ASK_CSS`; soften `ASK_CSS`; `render_briefing_pdf` passes `theme`. Do NOT touch `render_briefing_clinical_pdf` (fpdf2 fallback, out of scope).

**Files:**
- Modify: `neuro_caseboard/briefing_pdf.py:136` (`build_briefing_html`), `:165` (`render_briefing_pdf`), `ASK_CSS` (line 24)
- Test: `tests/test_briefing_pdf.py`

**Interfaces:**
- Produces: `build_briefing_html(result, *, title, subtitle="", …, theme="signal") -> str`; `render_briefing_pdf(result, out_path, *, title, subtitle="", …, theme="signal") -> str`.

- [ ] **Step 1: Write the failing test** — mirror Task 2's test against `build_briefing_html` using the file's existing `result` fixture/builder:

```python
def test_build_briefing_html_signal_dark_print_light(_min_result):
    dark = build_briefing_html(_min_result, title="Q", theme="signal")
    light = build_briefing_html(_min_result, title="Q", theme="print")
    assert "--bg:#000000" in dark and "--bg:#ffffff" in light


def test_build_briefing_html_defaults_to_signal(_min_result):
    assert "--bg:#000000" in build_briefing_html(_min_result, title="Q")
```

- [ ] **Step 2: Run the test, verify it fails** — `pytest -q tests/test_briefing_pdf.py` → FAIL.

- [ ] **Step 3: Implement** — add `theme="signal"` to both signatures; change the CSS join to `base_css(theme), ASK_CSS` (import `base_css`); pass `theme` in `render_briefing_pdf`; soften `ASK_CSS` brutalist borders/shadows/radius to tokens.

- [ ] **Step 4: Run the test, verify it passes** — `pytest -q tests/test_briefing_pdf.py` → PASS.

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_pdf.py tests/test_briefing_pdf.py
git commit -m "feat(pdf): thread theme through the briefing HTML builder"
```

---

### Task 4: Style routing — `CASEBOARD_PDF_STYLE` → theme (pipeline.py)

`render_case_pdf` (:330) and `render_ask_pdf` (:354) read `CASEBOARD_PDF_STYLE` (default `"exec"`) and call the HTML renderer or fall back to fpdf2. Map the style to a theme and a path: `signal`/`print`/`exec` → HTML renderer with `theme` (`exec`→`signal`); `clinical` → fpdf2 fallback; Chromium-missing → fpdf2 fallback (unchanged). Change the default from `"exec"` to `"signal"`.

**Files:**
- Modify: `neuro_caseboard/pipeline.py:330-352` (`render_case_pdf`), `:354-376` (`render_ask_pdf`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `render_caseboard_pdf(..., theme=…)`, `render_briefing_pdf(..., theme=…)` from Tasks 2–3.
- Behavior: a helper `_pdf_theme(style) -> str | None` returns `"signal"`/`"print"` for HTML themes, or `None` for `clinical` (→ fpdf2). `exec`/unset → `"signal"`.

- [ ] **Step 1: Write the failing test** — monkeypatch the HTML renderer to capture the `theme` it's called with (no Chromium needed):

```python
def test_render_case_pdf_routes_style_to_theme(monkeypatch, tmp_path, _min_dossier):
    calls = {}
    def fake_render(dossier, path, *, subtitle="", theme="signal"):
        calls["theme"] = theme; open(path, "wb").write(b"%PDF-1.4"); return str(path)
    monkeypatch.setattr("neuro_caseboard.caseboard_pdf.render_caseboard_pdf", fake_render)

    monkeypatch.delenv("CASEBOARD_PDF_STYLE", raising=False)           # default → signal
    render_case_pdf(_min_dossier, "topic", tmp_path / "a.pdf"); assert calls["theme"] == "signal"
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "print")
    render_case_pdf(_min_dossier, "topic", tmp_path / "b.pdf"); assert calls["theme"] == "print"
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "exec")                  # legacy → signal
    render_case_pdf(_min_dossier, "topic", tmp_path / "c.pdf"); assert calls["theme"] == "signal"
```

(If `_min_dossier` isn't shared, build the smallest valid `Dossier` inline as the file's other tests do.)

- [ ] **Step 2: Run the test, verify it fails** — `pytest -q tests/test_pipeline.py::test_render_case_pdf_routes_style_to_theme` → FAIL.

- [ ] **Step 3: Implement** — add `_pdf_theme(style)`; in both `render_case_pdf`/`render_ask_pdf`, default the env read to `"signal"`, compute `theme = _pdf_theme(style)`; when `theme` is not None and Chromium import succeeds, call the HTML renderer with `theme=theme`; else (`clinical` or import/launch failure) keep the existing fpdf2 fallback.

- [ ] **Step 4: Run the test, verify it passes** — `pytest -q tests/test_pipeline.py` → PASS (run the whole file to catch regressions in the existing fallback tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/pipeline.py tests/test_pipeline.py
git commit -m "feat(pdf): route CASEBOARD_PDF_STYLE to signal/print theme (default signal)"
```

---

### Task 5: Ship it — Chromium in the Docker image + compose default

So the deployed `/api/build/pdf` renders the dark HTML path instead of the fpdf2 fallback (the container currently has no Playwright/Chromium). NOTE: no pytest covers a Dockerfile; this task leaves the harness green trivially. **Real verification is post-merge** (`docker compose build && up -d`, then a container `/api/build/pdf` render check) — recorded in the loop's post-merge step, not the harness.

**Files:**
- Modify: `Dockerfile` (py-build stage installs `.[briefing]`; runtime stage installs Chromium)
- Modify: `docker-compose.yml` (add `CASEBOARD_PDF_STYLE: ${CASEBOARD_PDF_STYLE:-signal}` to the service env, for explicitness)

**Interfaces:** none (infra).

- [ ] **Step 1: Edit the Dockerfile** — in the `py-build` stage, ensure the briefing extra is installed (e.g. `pip install .[briefing]` or add `playwright` to the installed set so it lands in `/opt/venv`). In the `runtime` stage, after the venv COPY, add: `RUN playwright install --with-deps chromium` (PATH already includes `/opt/venv/bin`). Keep `libgomp1`.

- [ ] **Step 2: Add the compose default** — add `CASEBOARD_PDF_STYLE: ${CASEBOARD_PDF_STYLE:-signal}` under the `caseboard` service `environment:` block in `docker-compose.yml`.

- [ ] **Step 3: Verify the harness still passes** (the Python tests are unaffected): `cd <worktree> && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/test_exec_navy.py tests/test_caseboard_pdf.py tests/test_briefing_pdf.py tests/test_pipeline.py` → PASS.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "build(pdf): add Playwright Chromium to the image so the deployed app renders the dark HTML PDF"
```

---

## Post-merge verification (NOT a harness step — done by the loop driver after MERGE)

1. `docker compose build && docker compose up -d` (the `image:`+`build:` gotcha — must build, not pull).
2. Confirm the container now has Chromium: `docker exec … python3 -c "import playwright"` succeeds.
3. `POST /api/build/pdf` for a sample topic; confirm the returned PDF is the **HTML dark** render (not the brutalist fpdf2 fallback) — e.g. first-page PNG eyeball, or assert the response is larger / styled.
4. Render a `CASEBOARD_PDF_STYLE=print` PDF and eyeball it (light, ink-friendly).
