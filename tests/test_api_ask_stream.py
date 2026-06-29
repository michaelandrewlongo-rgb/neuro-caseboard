"""POST /api/ask/start returns a job id; the SSE stream replays the event log idempotently."""
import json
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _events_from_sse(text):
    out = []
    for line in text.splitlines():
        if line.startswith("data:"):
            out.append(json.loads(line[len("data:"):].strip()))
    return out


def _fake_stream_answer(question, emit, **kwargs):
    # neuro_core Citation is what the serializer expects for sources/answer.
    from neuro_core.synthesize import Citation
    cite = Citation(n=1, book="BookA", chapter="Ch1", page=10, text="t")
    emit({"type": "sources", "citations": [cite]})
    emit({"type": "figures", "figures": []})
    emit({"type": "answer_delta", "text": "Hel"})
    emit({"type": "answer_delta", "text": "lo [1]"})
    emit({"type": "answer", "answer": "Hello [1]", "citations": [cite],
          "figures": [], "refusal": False})
    emit({"type": "literature", "literature": None})
    emit({"type": "verification", "verification": None})
    emit({"type": "done"})


def test_start_then_stream_replays_full_log(monkeypatch):
    import api.server as server
    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)

    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    assert job_id

    body = client.get(f"/api/ask/stream/{job_id}?cursor=0").text
    events = _events_from_sse(body)
    assert [e["type"] for e in events][-1] == "done"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["answer"] == "Hello [1]"
    sources = next(e for e in events if e["type"] == "sources")
    assert sources["citations"][0]["book"] == "BookA"          # serialized via _citation_dict


def test_stream_from_cursor_is_idempotent(monkeypatch):
    import api.server as server
    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]

    full = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=0").text)
    # Reconnect from a later cursor → only the tail, no duplicates of earlier events.
    tail = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=3").text)
    assert tail == full[3:]


def test_unknown_job_404():
    import api.server as server
    client = TestClient(server.app)
    assert client.get("/api/ask/stream/nope?cursor=0").status_code == 404
