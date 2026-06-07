import pytest
from fastapi import HTTPException

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


def test_healthz_cold(monkeypatch):
    """A warm failure must not stop the server; /healthz reports warm=False."""
    import server.main as m
    from fastapi.testclient import TestClient

    def boom(config=None):
        raise RuntimeError("no GPU")

    monkeypatch.setattr(m, "get_engine", boom)
    with TestClient(m.app) as client:
        assert client.get("/healthz").json() == {"warm": False}


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
        # Starlette's router rejects percent-encoded separators before the handler.
        assert client.get("/figures/..%2f..%2fsecret.txt").status_code == 404


def test_figure_guard_rejects_separator_names():
    """Directly exercise the `safe != name` guard branch (a URL with separators is
    404'd by the router before reaching the handler, so call the handler itself)."""
    import server.main as m
    with pytest.raises(HTTPException) as exc:
        m.figure("../secret.txt")
    assert exc.value.status_code == 404


def test_figures_rejects_symlink_escape(monkeypatch, tmp_path):
    """A symlink inside assets_dir pointing outside it must not be served."""
    import server.main as m
    from fastapi.testclient import TestClient
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "leak.png").symlink_to(outside)
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    monkeypatch.setattr(m.CONFIG, "assets_dir", assets)
    with TestClient(m.app) as client:
        assert client.get("/figures/leak.png").status_code == 404


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
