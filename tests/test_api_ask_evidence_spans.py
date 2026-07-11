"""SP0: the /api/ask response and the citation dict must carry the §3.3 sidecar + folio."""
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402


def test_api_ask_carries_evidence_spans(monkeypatch):
    import api.server as server
    from neuro_caseboard.qa import QAResult
    from neuro_caseboard.evidence_spans import EvidenceSpan

    fake = QAResult(
        answer="Claim [1].", citations=[], figures=[], literature=None,
        evidence_spans=[EvidenceSpan(claim="Claim [1].", marker="1",
                                     quote="the verbatim sentence", matched=True, score=1.0)])
    monkeypatch.setattr("neuro_caseboard.qa.answer_question", lambda *a, **k: fake)

    body = TestClient(server.app).post("/api/ask", json={"question": "q"}).json()
    assert body["kind"] == "answer"
    assert body["evidence_spans"] == [{
        "claim": "Claim [1].", "marker": "1",
        "quote": "the verbatim sentence", "matched": True, "score": 1.0}]


def test_api_ask_evidence_spans_empty_when_absent(monkeypatch):
    import api.server as server
    from neuro_caseboard.qa import QAResult

    fake = QAResult(answer="Plain answer.", citations=[], figures=[], literature=None)
    monkeypatch.setattr("neuro_caseboard.qa.answer_question", lambda *a, **k: fake)
    body = TestClient(server.app).post("/api/ask", json={"question": "q"}).json()
    assert body["evidence_spans"] == []
