"""API closed loop via FastAPI TestClient (offline build flags)."""
import json
from fastapi.testclient import TestClient
from api.server import app


def test_feedback_remembers_and_updates_board(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEBOARD_PREFS_STORE", str(tmp_path / "prefs.json"))
    client = TestClient(app)

    r = client.post("/api/feedback", json={
        "topic": "C5-6 corpectomy", "enrich": False, "use_llm": False,
        "items": [{"mark": "missing",
                   "text": "Confirm intraoperative monitoring troubleshooting plan zenith",
                   "section": "Operative Plan"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "dossier" and body["remembered"] >= 1
    assert body["build_id"]                                   # rebuilt board cached → Download PDF matches the screen
    assert "zenith" in json.dumps(body["dossier"])           # board updated immediately

    pr = client.get("/api/preferences").json()
    assert pr["count"] >= 1 and pr["preferences"][0]["profile"] == "spine"

    # the memory generalizes to a fresh build of the same profile
    b = client.post("/api/build", json={
        "topic": "C3-4 ACDF", "enrich": False, "use_llm": False, "use_prefs": True}).json()
    assert "zenith" in json.dumps(b["dossier"])

    # use_prefs=False ignores the store (unchanged default behavior)
    b2 = client.post("/api/build", json={
        "topic": "C3-4 ACDF", "enrich": False, "use_llm": False, "use_prefs": False}).json()
    assert "zenith" not in json.dumps(b2["dossier"])


def test_feedback_rejects_invalid_mark(monkeypatch, tmp_path):
    # An unknown mark is a client error → clean 422, not an uncaught 500 (honest degradation).
    monkeypatch.setenv("CASEBOARD_PREFS_STORE", str(tmp_path / "prefs.json"))
    client = TestClient(app)
    r = client.post("/api/feedback", json={
        "topic": "C5-6 corpectomy", "enrich": False, "use_llm": False,
        "items": [{"mark": "bogus", "text": "x"}]})
    assert r.status_code == 422
    assert r.json()["kind"] == "error"
