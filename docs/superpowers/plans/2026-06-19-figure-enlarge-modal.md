# Figure Enlarge Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit per-figure "Enlarge" control to every figure-rendering site in the Streamlit app so the anatomy in figures/schematics can be viewed full-size in a large modal.

**Architecture:** A new bare-imported helper module `app/figure_gallery.py` exposes one function, `figure_card(image_path, caption=None, *, key)`, that renders the inline image (stretched to its column) plus a "🔍 Enlarge" button; clicking the button opens an `st.dialog(width="large")` modal showing the same image stretched full-width with its caption. The four existing `st.image(...)` figure blocks in `app/streamlit_app.py` (Ask, Build board, Case, Cards) are refactored to call `figure_card(...)`, leaving the surrounding `_badge(...)` calls and the Cards try/except in place. Tests are hermetic: they use `streamlit.testing.v1.AppTest` driven over a real temp PNG (no corpus/LLM/network).

**Tech Stack:** Python 3.10+, Streamlit 1.56.0 (`st.dialog`, `streamlit.testing.v1.AppTest`), Pillow (test fixtures), pytest.

## Global Constraints

- Streamlit version floor: 1.56.0 (`st.dialog` + `AppTest.from_string`/`from_file` available). Copied verbatim from environment: `st.dialog(title, *, width='small'|'large', ...)`.
- Use the modern image sizing API `st.image(path, width="stretch")` in the new helper — NOT the deprecated `use_container_width=True` (Streamlit warns it is removed after 2025-12-31). `filterwarnings = ["default"]`, so warnings do not fail tests, but the new code must be clean.
- Presentation-only change: do NOT modify any module under `neuro_caseboard/` or `neuro_core/`. Engine behavior is untouched.
- `app/` is a script directory (no `__init__.py`); modules there are imported **bare** (e.g. `import signal_theme as sig`). The new module follows the same convention. `AppTest` does NOT auto-add `app/` to `sys.path`; tests must insert it.
- The button styling needs no theme code: `app/signal_theme.py` already styles `.stButton>button` globally, so a plain `st.button(...)` matches the Executive-Navy theme.
- `pyproject.toml` sets `pythonpath = ["."]`; run pytest from the worktree root so the worktree's source wins over any editable install.
- Harness for this loop: `python3 -m pytest -p no:cacheprovider -q tests/test_app_figures.py` (must exit 0).

---

## Tasks (project-loop step cursor)

Each `- [ ]` below is one subagent-sized task; the detailed **Step** breakdown lives under the
matching `### Task N` section. The loop's `step_cursor` indexes these two items only.

- [x] Task 1: `figure_gallery` helper + hermetic AppTest coverage
- [x] Task 2: Wire `figure_card` into the four figure sites + app-boot smoke

---

### Task 1: `figure_gallery` helper + hermetic AppTest coverage

**Files:**
- Create: `app/figure_gallery.py`
- Create (Test): `tests/test_app_figures.py`

**Interfaces:**
- Produces: `figure_card(image_path: str, caption: str | None = None, *, key: str) -> None` — renders an inline stretched image and a uniquely-keyed "🔍 Enlarge" button (`key=f"enlarge_{key}"`); the click handler invokes a module-level `@st.dialog("Figure", width="large")` function that renders the image at `width="stretch"` and `st.caption(caption)` when a caption is given.
- Consumes: nothing from earlier tasks.

**Verified facts (hold while writing the test):**
- `AppTest` exposes buttons via `at.button` (by `.label`) and captions via `at.caption` (by `.value`). There is **no** `at.image` accessor — assert the modal opened via the dialog's `st.caption`, not the image.
- Before the Enlarge click `at.caption` is empty; after `at.button[i].click().run()` the dialog body runs and the caption text appears in `at.caption`.

**Step 1: Write the failing test**

Create `tests/test_app_figures.py`:

```python
"""Hermetic AppTest coverage for the figure-enlarge control (app/figure_gallery.py).

These tests drive Streamlit's headless AppTest harness over a real temporary PNG, so no
corpus / LLM / network is touched. `app/` is a bare-import script dir, so we put it on sys.path.
"""
import sys
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _make_png(tmp_path: Path, name: str = "fig.png") -> str:
    p = tmp_path / name
    Image.new("RGB", (48, 32), (180, 40, 40)).save(p)
    return str(p)


def _gallery_script(image_paths_and_caps: list[tuple[str, str]]) -> str:
    """A standalone Streamlit script that renders one figure_card per (path, caption)."""
    items = repr(image_paths_and_caps)
    return f"""
import sys
sys.path.insert(0, {str(APP_DIR)!r})
from figure_gallery import figure_card
for i, (path, cap) in enumerate({items}):
    figure_card(path, caption=cap, key=f"fig_{{i}}")
"""


def test_each_figure_has_one_enlarge_button(tmp_path):
    img = _make_png(tmp_path)
    at = AppTest.from_string(_gallery_script([(img, "Figure A")]))
    at.run()
    assert len(at.exception) == 0
    enlarge = [b for b in at.button if "Enlarge" in b.label]
    assert len(enlarge) == 1
    # The blow-up caption is NOT visible until the modal is opened.
    assert "Figure A" not in [c.value for c in at.caption]


def test_clicking_enlarge_opens_modal_with_full_size_caption(tmp_path):
    img = _make_png(tmp_path)
    at = AppTest.from_string(_gallery_script([(img, "Figure A")]))
    at.run()
    enlarge = [b for b in at.button if "Enlarge" in b.label]
    enlarge[0].click().run()
    assert len(at.exception) == 0
    # Dialog body ran -> its st.caption is now present.
    assert "Figure A" in [c.value for c in at.caption]


def test_multiple_figures_get_distinct_enlarge_buttons(tmp_path):
    a = _make_png(tmp_path, "a.png")
    b = _make_png(tmp_path, "b.png")
    at = AppTest.from_string(_gallery_script([(a, "Cap A"), (b, "Cap B")]))
    at.run()
    # No DuplicateWidgetID: distinct keys -> two buttons, no exception.
    assert len(at.exception) == 0
    enlarge = [btn for btn in at.button if "Enlarge" in btn.label]
    assert len(enlarge) == 2
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_app_figures.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'figure_gallery'` (the helper does not exist yet).

**Step 3: Write minimal implementation**

Create `app/figure_gallery.py`:

```python
"""Reusable figure card: an inline (column-width) image plus an explicit "Enlarge" control
that opens a large modal showing the image full-size. Used by every figure-rendering lane in
streamlit_app.py (Ask, Build board, Case, Cards) so anatomy can actually be read.

Imported bare (``import figure_gallery``) to match signal_theme — app/ is a script dir on
sys.path, not a package.
"""
import streamlit as st


@st.dialog("Figure", width="large")
def _enlarge_dialog(image_path: str, caption: str | None) -> None:
    """Modal body: the same image at full modal width, with its caption beneath."""
    st.image(image_path, width="stretch")
    if caption:
        st.caption(caption)


def figure_card(image_path, caption: str | None = None, *, key: str) -> None:
    """Render an inline figure with an "Enlarge" button that opens a full-size modal.

    Args:
        image_path: path (or object) accepted by ``st.image``.
        caption: optional caption shown under both the inline image and the enlarged image.
        key: caller-unique string; used to namespace the Enlarge button's widget key so
            multiple figures on one page do not collide.
    """
    st.image(image_path, caption=caption, width="stretch")
    if st.button("🔍 Enlarge", key=f"enlarge_{key}", width="stretch"):
        _enlarge_dialog(image_path, caption)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_app_figures.py`
Expected: PASS — 3 passed.

**Step 5: Commit**

```bash
git add app/figure_gallery.py tests/test_app_figures.py
git commit -m "loop step 0: figure_gallery helper + Enlarge modal (hermetic AppTest)"
```

---

### Task 2: Wire `figure_card` into the four figure sites + app-boot smoke

**Files:**
- Modify: `app/streamlit_app.py` (Ask, Build board, Case, Cards figure blocks; add the bare import)
- Modify (Test): `tests/test_app_figures.py` (append an app-boot smoke test)

**Interfaces:**
- Consumes: `figure_card(image_path, caption=None, *, key)` from Task 1.
- Produces: nothing new (call-site refactor).

**Exact edits to `app/streamlit_app.py`:**

1. Add the import next to `import signal_theme as sig` (top of file, after line 19):

```python
import signal_theme as sig
from figure_gallery import figure_card
```

2. **Ask** lane — replace the figure loop (currently `st.image(f.image_path, caption=..., use_container_width=True)` + `_badge(...)`):

```python
        if result.figures:
            sig.section("Figures", "FIG")
            cols = st.columns(min(3, len(result.figures)))
            for i, (col, f) in enumerate(zip(cols, result.figures)):
                with col:
                    figure_card(f.image_path,
                                caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                                key=f"ask_{i}")
                    _badge(from_figure(f).key, label)
```

3. **Build board** lane — replace the figure loop:

```python
        if view.figures:
            sig.section("Figures", "FIG")
            cols = st.columns(min(3, len(view.figures)))
            for i, (col, fig) in enumerate(zip(cols, view.figures)):
                with col:
                    figure_card(fig.image_path,
                                caption=f"[{fig.fig_id}] {fig.caption} — {fig.citation}",
                                key=f"build_{i}")
                    _badge(from_figure_item(fig).key, label)
```

4. **Case** lane — replace the schematics loop:

```python
            if view.figures:
                sig.section("Case schematics", "FIG")
                cols = st.columns(min(2, len(view.figures)))
                for i, (col, fig) in enumerate(zip(cols, view.figures)):
                    with col:
                        figure_card(fig.image_path, caption=fig.caption, key=f"case_{i}")
```

5. **Cards** lane — replace the inner image loop (preserve the try/except fallback):

```python
                for j, p in enumerate(c.image_paths):
                    try:
                        figure_card(p, key=f"cards_{i}_{j}")
                    except Exception:
                        st.caption(f"(image unavailable: {p})")
```

(`i` is the 1-based card index from `enumerate(res.cards if res else [], 1)`; `j` namespaces multiple images within a card. Cards images carry no caption — `figure_card`'s caption defaults to `None`.)

**Step 1: Write the failing test (append to `tests/test_app_figures.py`)**

```python
def test_app_boots_headlessly_after_refactor():
    """The full app still imports and renders in the default (Ask) lane with no input.

    Guards the four-site figure_card refactor: a bad import or signature mismatch surfaces as
    an AppTest exception. No query is fired (ask box empty), so no corpus/LLM is touched.
    """
    app_py = str(APP_DIR / "streamlit_app.py")
    at = AppTest.from_file(app_py, default_timeout=30).run()
    assert len(at.exception) == 0
    assert at.radio[0].options == ["Ask", "Build board", "Case", "Cards"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_app_figures.py::test_app_boots_headlessly_after_refactor`
Expected: FAIL — before the import line is added, the app raises (or, if run before edits, the assertion guards the refactor). Specifically, if the `from figure_gallery import figure_card` import is missing while the body calls `figure_card`, the app raises `NameError` and `len(at.exception) == 1`.

> Note: write this test BEFORE editing `streamlit_app.py`'s body so it fails first; or, if editing import + first call-site together, confirm the failure mode by temporarily omitting the import. The deliverable is: test red, then green after all five edits land.

**Step 3: Apply the five edits above to `app/streamlit_app.py`**

Apply edits 1–5 exactly as specified in this task's "Exact edits" section.

**Step 4: Run the full harness to verify it passes**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_app_figures.py`
Expected: PASS — 4 passed. Also confirm no figure block still calls the deprecated API:
Run: `grep -n use_container_width app/streamlit_app.py`
Expected: no figure-block matches remain (PDF/checkbox lines unaffected; if any non-figure `use_container_width` exists it is out of scope and may remain).

**Step 5: Commit**

```bash
git add app/streamlit_app.py tests/test_app_figures.py
git commit -m "loop step 1: route all four figure lanes through figure_card Enlarge control"
```

---

## Self-Review

**1. Spec coverage:** Goal = enlarge figures in Ask/Build/Card (and Case for consistency). Task 1 builds the enlarge control + modal; Task 2 wires it into all four lanes. ✔
**2. Placeholder scan:** All steps contain real code/commands and verified expected output. No TBD/TODO. ✔
**3. Type consistency:** `figure_card(image_path, caption=None, *, key)` and `_enlarge_dialog(image_path, caption)` signatures match between Task 1 (definition) and Task 2 (call sites). Keys are unique per lane (`ask_{i}`, `build_{i}`, `case_{i}`, `cards_{i}_{j}`). ✔
