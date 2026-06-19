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


def test_app_boots_headlessly_after_refactor():
    """The full app still imports and renders in the default (Ask) lane with no input.

    Guards the four-site figure_card refactor: a bad import or signature mismatch surfaces as
    an AppTest exception. No query is fired (ask box empty), so no corpus/LLM is touched.
    """
    app_py = str(APP_DIR / "streamlit_app.py")
    at = AppTest.from_file(app_py, default_timeout=30).run()
    assert len(at.exception) == 0
    assert at.radio[0].options == ["Ask", "Build board", "Case", "Cards"]
