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


def test_corpus_event_serializes_to_source_cards():
    """A Lane C ([D#]) corpus event → JSON source cards with a resolvable link; the passage
    content is NOT leaked to the wire (it's the server-side verification premise)."""
    import api.server as server
    from neuro_caseboard.corpus import CorpusRecord
    rec = CorpusRecord(work_id="w1", title="TESLA", journal="JAMA", year=2024,
                       study_design="rct", section_type="results", content="SECRET premise",
                       doi="10.1/x", pmid="40000001", source_db="cerebrovascular")
    out = server._serialize_ask_event({"type": "corpus", "corpus": [rec]})
    assert out["type"] == "corpus" and len(out["corpus"]) == 1
    card = out["corpus"][0]
    assert card["title"] == "TESLA" and card["link"] == "https://doi.org/10.1/x"
    assert "SECRET premise" not in json.dumps(card)  # content stays server-side


def test_cerebrovascular_flag_scopes_corpus_config_on_stream_start(monkeypatch):
    import api.server as server
    captured = {}

    def _fake_stream_answer(question, emit, **kwargs):
        captured.update(kwargs)
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start",
                         json={"question": "q", "cerebrovascular": True}).json()["job_id"]
    client.get(f"/api/ask/stream/{job_id}?cursor=0")  # drive the job thread to completion

    cfg = captured.get("corpus_config")
    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.dbs == ["cv_curated"]


def test_cerebrovascular_flag_defaults_off(monkeypatch):
    import api.server as server
    captured = {}

    def _fake_stream_answer(question, emit, **kwargs):
        captured.update(kwargs)
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    client.get(f"/api/ask/stream/{job_id}?cursor=0")
    assert captured.get("corpus_config") is None


def test_evidence_event_serializes(monkeypatch):
    """An 'evidence' domain event → JSON spans on the wire (quote is display copy)."""
    import api.server as server
    from neuro_caseboard.evidence_spans import EvidenceSpan

    def fake(question, emit, **kwargs):
        emit({"type": "evidence", "evidence_spans": [
            EvidenceSpan(claim="c [1]", marker="1", quote="q", matched=True, score=1.0)]})
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", fake)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    events = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=0").text)
    ev = next(e for e in events if e["type"] == "evidence")
    assert ev["evidence_spans"][0]["quote"] == "q"
    assert ev["evidence_spans"][0]["matched"] is True


def test_decision_event_serializes(monkeypatch):
    """A 'decision' domain event → the Decision Card JSON on the wire (streaming path)."""
    import api.server as server
    from neuro_caseboard.claim_review import DecisionCard, ReviewedClaim

    def fake(question, emit, **kwargs):
        emit({"type": "decision", "decision_card": DecisionCard(
            prose="It is indicated [1].",
            bottom_line=[ReviewedClaim(text="It is indicated.", markers=["1"],
                                       category="indication", quote="q", span_matched=True,
                                       status="settled")],
            coverage_gaps=["did not address: beta"])})
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", fake)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    events = _events_from_sse(client.get(f"/api/ask/stream/{job_id}?cursor=0").text)
    dc = next(e for e in events if e["type"] == "decision")["decision_card"]
    assert dc["prose"] == "It is indicated [1]."
    assert dc["bottom_line"][0]["category"] == "indication"
    assert dc["coverage_gaps"] == ["did not address: beta"]
