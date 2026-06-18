from __future__ import annotations

import json

from eval.monitor.contracts import Issue
from eval.monitor.detect import build_boards, run_detection, write_cards
from eval.monitor.detectors.coverage_drop import CoverageDropDetector

CID = "spine_acdf_c56"


def test_build_boards_calls_build_fn_k_times():
    calls = []
    boards = build_boards("query", 3, lambda q: calls.append(q) or "board")
    assert boards == ["board", "board", "board"]
    assert calls == ["query", "query", "query"]


def test_run_detection_flags_empty_boards():
    cases = [{"id": CID, "case_query": "C5-6 ACDF"}]
    issues = run_detection(
        cases, baseline={}, detectors=[CoverageDropDetector()],
        k=2, build_fn=lambda q: "- ✓ nothing relevant",
    )
    assert len(issues) == 1
    assert issues[0].kind == "coverage_drop"


def test_write_cards_emits_fingerprint_named_json(tmp_path):
    iss = Issue(kind="coverage_drop", severity="high", title="t", evidence=[],
                locus="author", proposed_tier="knob-only", proposed_fix="f",
                fingerprint="fp1")
    paths = write_cards([iss], tmp_path, run_id="run-1", git_sha="deadbeef")
    assert paths == [tmp_path / "fp1.json"]
    card = json.loads((tmp_path / "fp1.json").read_text())
    assert card["status"] == "new"
    assert card["provenance"] == {"run_id": "run-1", "git_sha": "deadbeef"}
    assert card["kind"] == "coverage_drop"
