"""The FastAPI server serves the built web SPA at root (single-process local deploy).

The `/api/*` routes keep precedence; unknown non-API paths fall back to index.html so
client-side routes (/ask, /build, /cards) survive a hard refresh. When the web app has not
been built (no web/dist), the server stays honest: the API still works and the root returns
a clear "not built" message instead of a confusing 404 or a blank page.
"""
import json

from fastapi.testclient import TestClient

from api.server import app


def _make_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>Neuro Caseboard</title><div id=\"root\"></div>"
    )
    (dist / "assets" / "app.js").write_text("console.log('hello')")
    (dist / "favicon.svg").write_text("<svg/>")
    return dist


def test_server_serves_spa_when_built(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("NEURO_CASEBOARD_WEB_DIST", str(dist))
    client = TestClient(app)

    # Root serves the SPA shell.
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text

    # Client-side route → SPA fallback to index.html (not a 404).
    r = client.get("/ask")
    assert r.status_code == 200
    assert 'id="root"' in r.text

    # A real built asset is served with the right content.
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log('hello')" in r.text

    # favicon (a real file at the dist root) is served, not the index fallback.
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert "<svg" in r.text

    # The API still wins over the SPA catch-all.
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_server_honest_when_web_not_built(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_WEB_DIST", str(tmp_path / "does-not-exist"))
    client = TestClient(app)

    # Root degrades honestly instead of 404/blank.
    r = client.get("/")
    assert r.status_code == 503
    body = r.json()
    assert body["kind"] == "unavailable"
    assert "build" in json.dumps(body).lower()

    # The API is unaffected by the missing web build.
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_unknown_api_route_is_not_swallowed_by_spa(tmp_path, monkeypatch):
    # An unknown /api/* path must not return the SPA HTML — it should stay a JSON 404,
    # so a typo'd endpoint is an honest API error, not a silent HTML page.
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("NEURO_CASEBOARD_WEB_DIST", str(dist))
    client = TestClient(app)

    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert "id=\"root\"" not in r.text
