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


# --- Real per-lane contract coverage (drives the SHIPPED streamlit_app.py) ------------------
# The app-boot smoke test above boots with an EMPTY query, so the four in-lane figure loops in
# streamlit_app.py are never executed. The tests below actually run those loops: they inject FAKE
# engine functions into the real engine modules BEFORE AppTest.from_file imports the script, then
# drive each lane (set the widget value / click the build button) so the SHIPPED
#   figure_card(..., key=f"ask_{i}" | f"build_{i}" | f"case_{i}" | f"cards_{i}_{j}")
# calls run against real figure data. Because we assert on the keys/captions emitted by the real
# file, a regressed per-lane key prefix (-> wrong enlarge_* widget key / DuplicateWidgetID) or a
# broken caption f-string is actually caught. Everything stays hermetic: no corpus / LLM / network
# (the fakes return lightweight objects pointing at a real temp PNG).

import types  # noqa: E402

APP_PY = str(APP_DIR / "streamlit_app.py")


def _make_figs(img: str):
    """Two fake figure objects exposing every attribute the four lanes read off a figure."""
    f0 = types.SimpleNamespace(
        image_path=img, source_n=1, book="Greenberg", page=42,
        caption="Internal carotid artery", fig_id="F2", citation="Rhoton, 2002")
    f1 = types.SimpleNamespace(
        image_path=img, source_n=2, book="Greenberg", page=88,
        caption="Vertebral artery", fig_id="F3", citation="Rhoton, 2002")
    return [f0, f1]


# The exact caption strings the SHIPPED lanes build from f0's attributes (mirrored here only to
# assert against — the f-strings under test live in streamlit_app.py and are what actually run):
ASK_CAP_F0 = "[1] Greenberg, p.42 — Internal carotid artery"   # Ask:   f"[{source_n}] {book}, p.{page} — {caption}"
BUILD_CAP_F0 = "[F2] Internal carotid artery — Rhoton, 2002"    # Build: f"[{fig_id}] {caption} — {citation}"
CASE_CAP_F0 = "Internal carotid artery"                        # Case:  fig.caption (bare)


def _install_fake_engine(monkeypatch, img: str):
    """Patch every engine entrypoint the lanes call so the real streamlit_app.py runs offline.

    Returns the fake figure list so callers can compute expected captions/keys.
    """
    import neuro_caseboard.qa as qa
    import neuro_caseboard.board_view as bv
    import neuro_caseboard.pipeline as pipeline
    import neuro_caseboard.intake as intake
    import neuro_core.evidence as evidence
    import neuro_core.cards_query as cards_query

    figs = _make_figs(img)
    view = types.SimpleNamespace(
        summary=types.SimpleNamespace(supported=1, to_verify=0, quarantined=0),
        figures=figs, markdown="A grounded answer.")

    # Ask lane: answer_question(q) -> result with .figures / .answer / .citations / .literature
    ask_result = types.SimpleNamespace(
        answer="A grounded answer.", figures=figs, citations=[], literature=None)
    monkeypatch.setattr(qa, "answer_question", lambda *a, **k: ask_result, raising=True)

    # Build + Case lanes: build_dossier / build_case_dossier -> dossier; board_view -> view
    monkeypatch.setattr(
        pipeline, "build_dossier",
        lambda *a, **k: types.SimpleNamespace(sections=[]), raising=True)
    monkeypatch.setattr(
        pipeline, "build_case_dossier",
        lambda *a, **k: types.SimpleNamespace(
            sections=[types.SimpleNamespace(figures=figs)]), raising=True)
    monkeypatch.setattr(bv, "board_view", lambda *a, **k: view, raising=True)

    # PDF rendering (PDF-download checkbox defaults to checked) -> write a stub file, return path.
    def _fake_pdf(*args, **kwargs):
        path = kwargs.get("path", args[-1])
        Path(path).write_bytes(b"%PDF-1.4 stub")
        return str(path)
    monkeypatch.setattr(pipeline, "render_case_pdf", _fake_pdf, raising=True)

    # Case lane dictation parse.
    fake_case = types.SimpleNamespace(
        missing_critical=lambda: [], to_topic=lambda: "C5-6 ACDF")
    monkeypatch.setattr(intake, "parse_dictation", lambda *a, **k: fake_case, raising=True)
    monkeypatch.setattr(intake, "deterministic_parse", lambda *a, **k: fake_case, raising=True)

    # Cross-feature evidence store helpers (called per figure / per badge).
    monkeypatch.setattr(evidence, "from_figure",
                        lambda f: types.SimpleNamespace(key=f"k{id(f)}"), raising=True)
    monkeypatch.setattr(evidence, "from_figure_item",
                        lambda f: types.SimpleNamespace(key=f"k{id(f)}"), raising=True)
    monkeypatch.setattr(evidence, "record", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(evidence, "other_features", lambda *a, **k: [], raising=True)

    # Cards lane search.
    card = types.SimpleNamespace(
        deck_name="Anatomy deck", deck_full=None, tags="",
        question_text="What runs in the cavernous sinus?",
        answer_text="CN III, IV, V1, V2, VI and the ICA.",
        image_paths=[img, img])
    monkeypatch.setattr(cards_query, "cards_query",
                        lambda *a, **k: types.SimpleNamespace(cards=[card]), raising=True)
    monkeypatch.setattr(cards_query, "flagged_tags", lambda *a, **k: [], raising=True)
    return figs


def _enlarge_keys(at):
    return {b.key for b in at.button if isinstance(b.key, str) and b.key.startswith("enlarge_")}


def _inline_image_captions(at):
    """Captions of inline st.image elements (figure_card renders st.image(..., caption=...))."""
    caps = []
    for e in at.main:
        p = getattr(e, "proto", None)
        if p is not None and type(p).__name__ == "ImageList":
            caps.extend(im.caption for im in p.imgs if im.caption)
    return caps


def test_real_lanes_render_figure_cards_with_shipped_keys(monkeypatch, tmp_path):
    """Task 1+2: execute the four SHIPPED in-lane figure loops with non-empty figure data and
    assert each lane emits its exact per-lane figure_card key (no DuplicateWidgetID).

    Drives app/streamlit_app.py itself; a regressed key prefix in that file (e.g. ask_-> q_) makes
    the expected enlarge_* button key disappear and fails this test.
    """
    img = _make_png(tmp_path)
    _install_fake_engine(monkeypatch, img)

    # Ask lane (default mode): typing a question fires the lane; expect ask_0 / ask_1.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.text_input(key="ask_q").set_value("blood supply of the lateral medulla").run()
    assert len(at.exception) == 0
    assert {"enlarge_ask_0", "enlarge_ask_1"} <= _enlarge_keys(at)

    # Build board lane: switch mode, set the case, click Build board; expect build_0 / build_1.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.radio(key="mode").set_value("Build board").run()
    at.text_input(key="build_topic").set_value("C5-6 ACDF").run()
    [b for b in at.button if b.label == "Build board"][0].click().run()
    assert len(at.exception) == 0
    assert {"enlarge_build_0", "enlarge_build_1"} <= _enlarge_keys(at)

    # Case lane: switch mode, dictate, click Build case dossier; expect case_0 / case_1.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.radio(key="mode").set_value("Case").run()
    at.text_area(key="case_dictation").set_value("62yo cervical myelopathy; plan ACDF.").run()
    [b for b in at.button if b.label == "Build case dossier"][0].click().run()
    assert len(at.exception) == 0
    assert {"enlarge_case_0", "enlarge_case_1"} <= _enlarge_keys(at)

    # Cards lane: switch mode, search; the one fake card has two images -> cards_1_0 / cards_1_1.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.radio(key="mode").set_value("Cards").run()
    at.text_input(key="cards_q").set_value("cavernous sinus contents").run()
    assert len(at.exception) == 0
    assert {"enlarge_cards_1_0", "enlarge_cards_1_1"} <= _enlarge_keys(at)


def test_real_lane_caption_format_strings(monkeypatch, tmp_path):
    """Task 1: the SHIPPED per-lane caption f-strings render verbatim from real figure data.

    A broken caption format string in streamlit_app.py changes the emitted caption and fails here.
    The Ask lane (gated on a persistent text input) is checked via the Enlarge modal's st.caption;
    Build/Case (gated on a one-shot build button) are checked via their inline st.image caption,
    asserted on the same run the button is pressed.
    """
    img = _make_png(tmp_path)
    _install_fake_engine(monkeypatch, img)

    # Ask lane caption: f"[{source_n}] {book}, p.{page} — {caption}". Inline + modal.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.text_input(key="ask_q").set_value("blood supply of the lateral medulla").run()
    assert ASK_CAP_F0 in _inline_image_captions(at)            # inline image caption
    assert ASK_CAP_F0 not in [c.value for c in at.caption]     # st.caption hidden until modal opens
    at.button(key="enlarge_ask_0").click().run()
    assert len(at.exception) == 0
    assert ASK_CAP_F0 in [c.value for c in at.caption]         # modal st.caption now present

    # Build lane caption: f"[{fig_id}] {caption} — {citation}". Inline image caption.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.radio(key="mode").set_value("Build board").run()
    at.text_input(key="build_topic").set_value("C5-6 ACDF").run()
    [b for b in at.button if b.label == "Build board"][0].click().run()
    assert len(at.exception) == 0
    assert BUILD_CAP_F0 in _inline_image_captions(at)

    # Case lane caption: bare fig.caption. Inline image caption.
    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.radio(key="mode").set_value("Case").run()
    at.text_area(key="case_dictation").set_value("62yo cervical myelopathy; plan ACDF.").run()
    [b for b in at.button if b.label == "Build case dossier"][0].click().run()
    assert len(at.exception) == 0
    assert CASE_CAP_F0 in _inline_image_captions(at)


def test_real_cards_lane_caption_none_renders_and_enlarges(monkeypatch, tmp_path):
    """Task 3: the SHIPPED Cards lane calls figure_card(path, key=...) with NO caption.

    Drive the real lane, open the Enlarge dialog, and confirm it works with caption=None: no
    exception, and the dialog's `if caption:` branch is skipped (no figure caption text emitted).
    """
    img = _make_png(tmp_path)
    _install_fake_engine(monkeypatch, img)

    at = AppTest.from_file(APP_PY, default_timeout=30).run()
    at.radio(key="mode").set_value("Cards").run()
    at.text_input(key="cards_q").set_value("cavernous sinus contents").run()
    assert len(at.exception) == 0
    assert "enlarge_cards_1_0" in _enlarge_keys(at)
    # The captioned-figure strings must never appear: the Cards lane passes caption=None.
    captions_before = [c.value for c in at.caption]
    assert CASE_CAP_F0 not in captions_before
    # Opening the modal with caption=None must not error and must emit no NEW figure caption.
    at.button(key="enlarge_cards_1_0").click().run()
    assert len(at.exception) == 0
    assert CASE_CAP_F0 not in [c.value for c in at.caption]
