"""POST /api/ask with cerebrovascular=true scopes Lane C to the curated corpus DB."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def test_blocking_ask_forwards_scoped_corpus_config(monkeypatch):
    import api.server as server
    captured = {}

    def _fake_answer_question(question, **kwargs):
        captured.update(kwargs)
        from neuro_caseboard.qa import QAResult
        return QAResult(answer="ok", citations=[], figures=[])

    monkeypatch.setattr("neuro_caseboard.qa.answer_question", _fake_answer_question)
    client = TestClient(server.app)
    resp = client.post("/api/ask", json={"question": "q", "cerebrovascular": True})
    assert resp.status_code == 200
    cfg = captured.get("corpus_config")
    assert cfg is not None and cfg.enabled is True and cfg.dbs == ["cv_curated"]
