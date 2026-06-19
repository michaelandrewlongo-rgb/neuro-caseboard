"""Hermetic unit tests for Ask claim-level confidence (app/ask_confidence.py), BACKLOG P2 #4.

Pure parsing/classification — no Streamlit, engine, corpus, LLM, or network. `app/` is a
bare-import script dir, so we put it on sys.path."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ask_confidence import (ClaimConfidence, split_claims, cited_sources,  # noqa: E402
                            classify, grade_answer, summarize, STATUS_LABEL, STATUS_MARK)

TEXTBOOK = "textbook"
LIT = "literature"


def test_cited_sources_extracts_ordered_unique_markers():
    assert cited_sources("The PICA supplies the lateral medulla [1][2].") == (1, 2)
    assert cited_sources("No citation here.") == ()
    assert cited_sources("Repeated [3] then again [3].") == (3,)


def test_split_claims_keeps_markers_with_their_sentence():
    claims = split_claims("First fact [1]. Second fact [2][3]. Third has none.")
    assert len(claims) == 3
    assert "[1]" in claims[0] and "[2][3]" in claims[1]


def test_classify_five_way_rule():
    lane = {1: TEXTBOOK, 2: TEXTBOOK, 3: LIT}
    assert classify((), lane, frozenset()) == "unsupported"
    assert classify((1, 2), lane, frozenset()) == "consensus"
    assert classify((1,), lane, frozenset()) == "single-source"
    assert classify((3,), lane, frozenset()) == "literature-only"
    assert classify((1, 3), lane, frozenset()) == "single-source"   # 1 textbook + lit
    assert classify((1, 2), lane, frozenset({2})) == "conflict"     # conflict wins


def test_grade_answer_labels_each_claim_and_preserves_not_found():
    answer = ("PICA supplies the lateral medulla [1][2]. "
              "Recent trials favor early surgery [3]. "
              "Some surgeons prefer a lateral approach.")
    lane = {1: TEXTBOOK, 2: TEXTBOOK, 3: LIT}
    claims = grade_answer(answer, lane)
    assert [c.status for c in claims] == ["consensus", "literature-only", "unsupported"]
    assert claims[0].sources == (1, 2)
    # explicit not-found preserved (still present, labelled unsupported)
    assert claims[2].text.strip().startswith("Some surgeons")


def test_summarize_counts_by_status():
    claims = [ClaimConfidence("a", "consensus", (1, 2)),
              ClaimConfidence("b", "unsupported", ())]
    assert summarize(claims) == {"consensus": 1, "unsupported": 1}


def test_status_label_and_mark_cover_all_five_statuses():
    for s in ("consensus", "single-source", "conflict", "literature-only", "unsupported"):
        assert s in STATUS_LABEL and s in STATUS_MARK


def test_ask_lane_renders_claim_confidence(monkeypatch):
    """The Ask lane grades the engine answer and renders per-claim markers + a summary, with no
    exception. Hermetic: engine stubbed, no corpus/LLM/network."""
    import pytest
    pytest.importorskip("streamlit")
    import neuro_caseboard.qa as qa

    class _Cite:
        def __init__(self, n): self.n = n

    class _Res:
        answer = "PICA supplies the lateral medulla [1][2]. Some surgeons prefer a lateral approach."
        citations = [_Cite(1), _Cite(2)]
        figures = []
        literature = None

    monkeypatch.setattr(qa, "answer_question", lambda question, **kw: _Res())

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30)
    at.session_state["ask_q"] = "blood supply of the lateral medulla"
    at.run()
    assert len(at.exception) == 0
    blob = " ".join(m.value for m in at.markdown)
    assert "consensus" in blob.lower()            # the summary line
    assert "not found in corpus" in blob.lower()  # the unsupported claim is shown, not dropped
