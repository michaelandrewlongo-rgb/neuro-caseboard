"""Unit tests for the Phase 0B placebo eval harness (eval/placebo_eval.py). Pure — no Vertex."""
from eval.placebo_eval import build_arms, grade_answer, summarize


def _rec(qid, domain, answer, narrative="", cites=None):
    return {"question_id": qid, "question": f"Q {qid}", "domain": domain, "answer": answer,
            "raw_response": {"literature": {"narrative": narrative, "citations": cites or []}}}


def _records():
    cites = [{"n": 1, "pmid": "111", "title": "T1", "journal": "Stroke", "year": 2024}]
    return [
        _rec("NIS-01", "Neurointerventional", "Core answer one. " * 40,
             narrative="Recent EVT trials expanded windows [L1]. " * 8, cites=cites),
        _rec("SPINE-01", "Spine", "Core answer two. " * 40,
             narrative="Fusion vs arthroplasty evidence [L1]. " * 8, cites=cites),
    ]


def test_build_arms_makes_four_arms_and_scrambles_cross_domain():
    arms = build_arms(_records())
    assert set(arms) == {"NIS-01", "SPINE-01"}
    a = arms["NIS-01"]["arms"]
    assert set(a) == {"core", "real", "placebo", "scramble"}
    assert a["core"] in a["real"] and len(a["real"]) > len(a["core"])     # appendix appended
    # scramble takes a DIFFERENT-domain question's appendix
    assert arms["NIS-01"]["scramble_from"] == "SPINE-01"


def test_placebo_length_matches_real_appendix():
    arms = build_arms(_records())
    a = arms["NIS-01"]["arms"]
    real_app = len(a["real"]) - len(a["core"])
    plac_app = len(a["placebo"]) - len(a["core"])
    assert abs(plac_app - real_app) <= 0.1 * real_app        # within 10% of real length
    assert "PubMed lane" in a["placebo"] and "[L1]" in a["placebo"]  # same shape


def test_records_without_appendix_are_skipped():
    recs = _records() + [_rec("X-1", "Trauma", "no lit here", narrative="", cites=[])]
    arms = build_arms(recs)
    assert "X-1" not in arms


def test_grade_answer_parses_and_recovers(monkeypatch):
    calls = {"n": 0}

    def flaky_complete(system, user, *, temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json"                      # first call fails -> retry
        return '{"score": 87, "letter": "B", "clinically_usable": "usable"}'

    out = grade_answer("q", "a", complete=flaky_complete)
    assert out["score"] == 87.0 and out["letter"] == "B"
    assert calls["n"] == 2                          # recovered on retry


def test_grade_answer_returns_error_after_retries():
    out = grade_answer("q", "a", complete=lambda *a, **k: "garbage")
    assert out["score"] is None and out["error"]


def test_summarize_computes_paired_deltas(tmp_path):
    rows = [
        {"qid": "Q1", "arm": "core", "score": 80.0}, {"qid": "Q1", "arm": "real", "score": 85.0},
        {"qid": "Q1", "arm": "placebo", "score": 84.0}, {"qid": "Q1", "arm": "scramble", "score": 83.0},
        {"qid": "Q2", "arm": "core", "score": 70.0}, {"qid": "Q2", "arm": "real", "score": 77.0},
        {"qid": "Q2", "arm": "placebo", "score": 76.0}, {"qid": "Q2", "arm": "scramble", "score": 75.0},
    ]
    summarize(rows, tmp_path)
    import json
    s = json.loads((tmp_path / "placebo-summary.json").read_text())
    assert s["mean_by_arm"]["real"] == 81.0
    assert s["real_minus_core"][0] == 6.0          # (5+7)/2
    assert s["real_minus_placebo"][0] == 1.0       # (1+1)/2  -> small => mostly format
