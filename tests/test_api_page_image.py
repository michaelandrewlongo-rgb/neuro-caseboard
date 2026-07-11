"""SP2b: /api/page-image renders a cited textbook page to PNG, whitelisted to CORPUS_DIR."""
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("fitz")

from fastapi.testclient import TestClient  # noqa: E402

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _make_corpus(tmp_path) -> Path:
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "TEST PAGE 1")
    doc.new_page().insert_text((72, 72), "TEST PAGE 2")
    doc.save(str(tmp_path / "TestBook.pdf"))
    doc.close()
    return tmp_path


def test_page_image_renders_png(tmp_path, monkeypatch):
    import api.server as server
    corpus = _make_corpus(tmp_path)
    monkeypatch.setattr(server, "_corpus_dir", lambda: corpus)
    r = TestClient(server.app).get("/api/page-image?book=TestBook&page=1")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == _PNG_MAGIC
    assert len(r.content) > 100


def test_page_image_second_page_and_clamp(tmp_path, monkeypatch):
    import api.server as server
    corpus = _make_corpus(tmp_path)
    monkeypatch.setattr(server, "_corpus_dir", lambda: corpus)
    client = TestClient(server.app)
    assert client.get("/api/page-image?book=TestBook&page=2").content[:8] == _PNG_MAGIC
    # A page past the end clamps to the last page rather than 404-ing.
    assert client.get("/api/page-image?book=TestBook&page=99").status_code == 200


def test_page_image_unknown_book_404(tmp_path, monkeypatch):
    import api.server as server
    monkeypatch.setattr(server, "_corpus_dir", lambda: tmp_path)
    assert TestClient(server.app).get("/api/page-image?book=Nope&page=1").status_code == 404


def test_page_image_rejects_traversal(tmp_path, monkeypatch):
    import api.server as server
    monkeypatch.setattr(server, "_corpus_dir", lambda: tmp_path)
    r = TestClient(server.app).get("/api/page-image", params={"book": "../../etc/passwd", "page": 1})
    assert r.status_code == 404


def test_page_image_no_corpus_dir_404(monkeypatch):
    import api.server as server
    monkeypatch.setattr(server, "_corpus_dir", lambda: None)   # query-only deploy: no PDFs on disk
    assert TestClient(server.app).get("/api/page-image?book=Youmans&page=10").status_code == 404
