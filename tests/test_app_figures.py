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


# --- Real per-lane contract coverage -------------------------------------------------------
# The app-boot smoke test above boots with an empty query, so the four lanes never reach
# figure_card. These tests replicate the EXACT key-format and caption-format strings that each
# lane in streamlit_app.py passes to figure_card(...), driving them through AppTest. This catches
# a regressed per-lane key (DuplicateWidgetID) or a broken caption f-string, hermetically — no
# corpus / LLM / network. The format strings below are mirrored verbatim from streamlit_app.py:
#   Ask:   key=f"ask_{i}"        caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}"
#   Build: key=f"build_{i}"      caption=f"[{fig.fig_id}] {fig.caption} — {fig.citation}"
#   Case:  key=f"case_{i}"       caption=fig.caption
#   Cards: key=f"cards_{i}_{j}"  (no caption — caption=None)

# (key, caption-or-None) pairs reproducing every lane's real figure_card(...) call.
# Multiple figures within a lane and across lanes, exactly as the app renders them.
_ASK_CAP = "[1] Greenberg, p.42 — Internal carotid artery"     # f"[{source_n}] {book}, p.{page} — {caption}"
_BUILD_CAP = "[F2] Circle of Willis — Rhoton, 2002"            # f"[{fig_id}] {caption} — {citation}"
_CASE_CAP = "Cavernous sinus contents"                         # fig.caption (bare)

_REAL_LANE_FIGURES = [
    ("ask_0", _ASK_CAP),
    ("ask_1", "[2] Greenberg, p.88 — Vertebral artery"),
    ("build_0", _BUILD_CAP),
    ("build_1", "[F3] Basal cisterns — Rhoton, 2002"),
    ("case_0", _CASE_CAP),
    ("case_1", "Meckel cave"),
    ("cards_1_0", None),   # Cards lane: enumerate(..., 1), no caption
    ("cards_1_1", None),
    ("cards_2_0", None),
]


def _real_lanes_script(img: str, figures: list[tuple[str, str | None]]) -> str:
    """Streamlit script replicating each lane's real figure_card(...) call (real keys/captions)."""
    items = repr([(img, key, cap) for key, cap in figures])
    return f"""
import sys
sys.path.insert(0, {str(APP_DIR)!r})
from figure_gallery import figure_card
for path, key, cap in {items}:
    if cap is None:
        figure_card(path, key=key)
    else:
        figure_card(path, caption=cap, key=key)
"""


def test_real_lane_key_scheme_is_collision_free(tmp_path):
    """The shipped per-lane key scheme (ask_/build_/case_/cards_ ) renders with no key collision.

    A constant key here raises StreamlitDuplicateElementKey (proven separately); the real
    per-lane formats must stay distinct, yielding exactly one Enlarge button per figure.
    """
    img = _make_png(tmp_path)
    at = AppTest.from_string(_real_lanes_script(img, _REAL_LANE_FIGURES))
    at.run()
    assert len(at.exception) == 0  # no DuplicateWidgetID across the four lanes' real keys
    enlarge = [b for b in at.button if "Enlarge" in b.label]
    assert len(enlarge) == len(_REAL_LANE_FIGURES)


def test_real_lane_caption_format_renders_in_modal(tmp_path):
    """Clicking a captioned lane's Enlarge opens the modal with that lane's formatted caption."""
    img = _make_png(tmp_path)
    at = AppTest.from_string(_real_lanes_script(img, _REAL_LANE_FIGURES))
    at.run()
    # Captioned lanes' caption strings are not shown until their modal opens.
    captions_before = [c.value for c in at.caption]
    assert _ASK_CAP not in captions_before
    assert _BUILD_CAP not in captions_before
    assert _CASE_CAP not in captions_before
    # Open the first (Ask lane) figure's modal and assert its exact formatted caption appears.
    enlarge = [b for b in at.button if "Enlarge" in b.label]
    enlarge[0].click().run()
    assert len(at.exception) == 0
    assert _ASK_CAP in [c.value for c in at.caption]


def test_cards_lane_caption_none_renders_and_enlarges(tmp_path):
    """The Cards lane calls figure_card(path, key=...) with no caption (caption=None).

    Assert it renders (one Enlarge, no exception) and that opening the dialog works while the
    `if caption:` branch is skipped — no caption text appears in the modal.
    """
    img = _make_png(tmp_path)
    at = AppTest.from_string(_real_lanes_script(img, [("cards_1_0", None)]))
    at.run()
    assert len(at.exception) == 0
    enlarge = [b for b in at.button if "Enlarge" in b.label]
    assert len(enlarge) == 1
    # Open the modal: dialog body runs, but with caption=None no st.caption is emitted.
    enlarge[0].click().run()
    assert len(at.exception) == 0
    assert len(at.caption) == 0
