"""The shared Executive-Navy print theme: the brand CSS tokens + the two pure helpers."""
import base64

from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, base_css, inline, img_data_uri


def test_inline_escapes_then_promotes_bold():
    assert inline("a <b> & **bold**") == "a &lt;b&gt; &amp; <b>bold</b>"


def test_img_data_uri_derives_mime_from_basename_only(tmp_path):
    p = tmp_path / "v1.2"
    p.mkdir()
    f = p / "figA.JPG"            # dotted parent dir must not corrupt the MIME
    f.write_bytes(b"\xff\xd8\xff")
    uri = img_data_uri(str(f))
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff"


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
