"""The shared Executive-Navy print theme: the brand CSS tokens + the two pure helpers."""
import base64

from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, inline, img_data_uri


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
    assert "--accent:#0e7490" in EXEC_NAVY_CSS
    assert "Archivo" in EXEC_NAVY_CSS and "IBM+Plex+Mono" in EXEC_NAVY_CSS
