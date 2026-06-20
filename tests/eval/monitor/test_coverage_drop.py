from __future__ import annotations

from eval.coverage import ANCHORS
from eval.monitor.contracts import RunArtifacts
from eval.monitor.detectors.coverage_drop import CoverageDropDetector

CID = "spine_acdf_c56"  # a real case id in eval/coverage.py ANCHORS


def _full_board() -> str:
    # one anchor from every must_cover item -> 100% coverage
    return " . ".join(anchors[0] for _label, anchors in ANCHORS[CID])


def test_flags_when_board_covers_nothing_and_no_baseline():
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: ["- ✓ no relevant clinical content here"]},
        baseline={},
    )
    issues = CoverageDropDetector(abs_floor=0.70).detect(art)
    assert len(issues) == 1
    iss = issues[0]
    assert iss.kind == "coverage_drop"
    assert iss.severity == "high"      # below floor
    assert iss.proposed_tier == "knob-only"
    assert len(iss.evidence) == len(ANCHORS[CID])  # everything missing
    assert iss.fingerprint


def test_silent_when_fully_covered_and_no_baseline():
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: [f"- ✓ {_full_board()}"]},
        baseline={},
    )
    assert CoverageDropDetector(abs_floor=0.70).detect(art) == []


def test_uses_worst_of_k_runs():
    # one perfect board, one empty board -> worst-of-K = 0% -> flagged
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: [f"- ✓ {_full_board()}", "- ✓ nothing"]},
        baseline={},
    )
    assert len(CoverageDropDetector(abs_floor=0.70).detect(art)) == 1


def test_relative_regression_against_baseline():
    # fully covered now (1.0) and baseline says 1.0 -> no regression
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: [f"- ✓ {_full_board()}"]},
        baseline={CID: {"coverage": 1.0}},
    )
    assert CoverageDropDetector().detect(art) == []
