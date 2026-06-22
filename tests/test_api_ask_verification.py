"""SHOULD-5: the /api/ask response must carry the verification block.

A light TestClient call with answer_question monkeypatched to return a QAResult holding a
known AnswerVerification proves the handler serializes verification (via verification_to_dict)
into the answer payload. fastapi is a core dependency, but the import is guarded for any
minimal environment that lacks it.
"""
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402


def test_api_ask_response_carries_verification(monkeypatch):
    import api.server as server
    from neuro_caseboard.qa import QAResult
    from neuro_caseboard.answer_verify import AnswerVerification, ClaimVerdict

    # 2 cited claims, 1 unsupported (marker "1") -> groundedness 0.5, unsupported_markers ["1"].
    verification = AnswerVerification(
        claims=[ClaimVerdict("Supported claim [1].", ["1"], True, 20),
                ClaimVerdict("Unsupported claim [1].", ["1"], False, 20)],
        n_cited_claims=2, n_unsupported=1)
    fake = QAResult(answer="Supported claim [1]. Unsupported claim [1].",
                    citations=[], figures=[], literature=None, verification=verification)

    # The /api/ask handler does `from neuro_caseboard.qa import answer_question` at call time,
    # so patch the source symbol on neuro_caseboard.qa (not api.server).
    monkeypatch.setattr("neuro_caseboard.qa.answer_question", lambda *a, **k: fake)

    client = TestClient(server.app)
    resp = client.post("/api/ask", json={"question": "what supplies Wernicke's area?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "answer"
    assert body["verification"] == {
        "n_cited_claims": 2,
        "n_unsupported": 1,
        "groundedness": 0.5,
        "unsupported_markers": ["1"],
    }


def test_api_ask_verification_null_when_absent(monkeypatch):
    """A QAResult without a verification (e.g. a path that did not attach one) serializes to
    a null verification field, never a fabricated block."""
    import api.server as server
    from neuro_caseboard.qa import QAResult

    fake = QAResult(answer="Plain answer.", citations=[], figures=[], literature=None,
                    verification=None)
    monkeypatch.setattr("neuro_caseboard.qa.answer_question", lambda *a, **k: fake)

    client = TestClient(server.app)
    resp = client.post("/api/ask", json={"question": "q"})
    assert resp.status_code == 200
    assert resp.json()["verification"] is None
