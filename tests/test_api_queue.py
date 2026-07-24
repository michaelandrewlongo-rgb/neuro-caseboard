"""Overnight case-brief queue: enqueue -> background worker -> durable result.

Runs fully offline: the 7-section synthesis uses the same FakeSynth/TextRetriever harness
as test_api_briefing.py, and _do_build_briefing is monkeypatched so no LLM/GPU/corpus is
touched. The queue DB is pointed at tmp_path by the autouse conftest fixture.
"""

import time as _time

from fastapi.testclient import TestClient

import api.server as server
from neuro_caseboard.pipeline import build_briefing_bundle


class FakeSynth:
    def generate(self, system, user, images, route=None):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        if key == "equipment":
            return "positioning_monitoring: prone; SSEP\nrefs: T1\n"
        if key == "modalities":
            return "### ACDF\nrole: decompress\npreferred: yes\nrefs: T1\n"
        return f"[critical] {key} claim {{T1}}\n"


class TRec:
    def __init__(self, n):
        self.id = f"rec-{n}"
        self.title = f"Youmans chapter {n}"
        self.source = "corpus"
        self.text = f"passage {n}"
        self.metadata = {"citation": f"Youmans p.{n}", "book": "Youmans", "page": n}


class TextRetriever:
    def retrieve(self, query, top_n=6, **kwargs):
        return [TRec(1)]


def _bundle():
    return build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                                 fig_retriever=None, synth_client=FakeSynth(),
                                 literature=False)


def _wait_done(client, job_id, timeout=15.0):
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        data = client.get(f"/api/queue/{job_id}").json()
        if data.get("status") in ("done", "error"):
            return data
        _time.sleep(0.05)
    raise AssertionError(f"brief {job_id} never finished: {data}")


def test_enqueue_builds_and_persists(monkeypatch):
    b = _bundle()
    monkeypatch.setattr(server, "_do_build_briefing", lambda *a, **k: b)
    client = TestClient(server.app)
    r = client.post("/api/queue", json={"case": "C5-6 ACDF", "use_prefs": False})
    assert r.status_code == 200
    job_id = r.json()["id"]

    data = _wait_done(client, job_id)
    assert data["status"] == "done"
    assert data["kind"] == "briefing" and data["briefing"]["sections"]

    # durable: listed with the brief available, straight from SQLite (no in-memory state)
    listed = client.get("/api/queue").json()["briefs"]
    mine = next(x for x in listed if x["id"] == job_id)
    assert mine["status"] == "done" and mine["brief_available"] is True
    assert mine["case"] == "C5-6 ACDF"


def test_worker_error_is_recorded_not_lost(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("synthesis exploded")
    monkeypatch.setattr(server, "_do_build_briefing", boom)
    client = TestClient(server.app)
    job_id = client.post("/api/queue", json={"case": "bad case"}).json()["id"]
    data = _wait_done(client, job_id)
    assert data["status"] == "error"
    assert "synthesis exploded" in data["error"]


def test_startup_requeues_crashed_running_brief(monkeypatch):
    b = _bundle()
    monkeypatch.setattr(server, "_do_build_briefing", lambda *a, **k: b)
    # Simulate a server that died mid-build: a row stuck in 'running'.
    conn = server._queue_conn()
    conn.execute(
        "INSERT INTO briefs (id, case_text, status, created_ts, enrich, use_llm, use_prefs) "
        "VALUES ('stuck1', 'orphaned case', 'running', ?, 0, 0, 0)", (_time.time(),))
    conn.commit()
    conn.close()

    client = TestClient(server.app)          # entering the context runs the startup hook
    with client:
        data = _wait_done(client, "stuck1")
        assert data["status"] == "done"


def test_empty_case_is_422():
    client = TestClient(server.app)
    r = client.post("/api/queue", json={"case": "   "})
    assert r.status_code == 422


def test_unknown_id_is_404():
    client = TestClient(server.app)
    assert client.get("/api/queue/nope").status_code == 404
    assert client.get("/api/queue/nope/pdf").status_code == 404


def test_pdf_absent_is_honest_404(monkeypatch):
    b = _bundle()
    monkeypatch.setattr(server, "_do_build_briefing", lambda *a, **k: b)
    client = TestClient(server.app)
    job_id = client.post("/api/queue", json={"case": "C5-6 ACDF"}).json()["id"]
    _wait_done(client, job_id)
    r = client.get(f"/api/queue/{job_id}/pdf")
    # Renderer (Playwright/Chromium) is absent in the test env -> no stored PDF, honest 404.
    if r.status_code == 404:
        assert "no PDF" in r.json()["error"]
    else:
        assert r.headers["content-type"] == "application/pdf"


def test_queue_page_served_before_spa_catchall():
    client = TestClient(server.app)
    r = client.get("/queue")
    assert r.status_code == 200
    assert "Overnight brief queue" in r.text
