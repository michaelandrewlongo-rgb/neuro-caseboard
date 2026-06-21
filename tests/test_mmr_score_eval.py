"""Unit test for the Phase 1-D score-effect summarizer (eval/mmr_score_eval.py). Pure."""
import json

from eval.mmr_score_eval import summarize


def test_summarize_paired_delta_and_skips(tmp_path):
    rows = [
        {"qid": "Q1", "score_off": 80.0, "score_on": 84.0},   # +4
        {"qid": "Q2", "score_off": 70.0, "score_on": 72.0},   # +2
        {"qid": "Q3", "score_off": 90.0, "score_on": 90.0},   # 0
        {"qid": "Q4", "skipped": "clarification", "score_off": None, "score_on": None},
    ]
    summarize(rows, 0.15, tmp_path)
    s = json.loads((tmp_path / "mmr-score-summary.json").read_text())
    assert s["n_paired"] == 3 and s["n_skipped"] == 1
    assert s["mean_delta_on_minus_off"] == 2.0     # (4+2+0)/3
    assert s["wins"] == 2 and s["losses"] == 0 and s["ties"] == 1
    assert s["mean_off"] == 80.0 and s["mean_on"] == 82.0
