from __future__ import annotations

import datetime

from eval.monitor.contracts import Issue
from eval.monitor.suppress import filter_suppressed, load_suppressions


def _issue(fp: str) -> Issue:
    return Issue(kind="coverage_drop", severity="low", title="t", evidence=[],
                 locus="author", proposed_tier="knob-only", proposed_fix="f",
                 fingerprint=fp)


def test_missing_file_returns_empty_set(tmp_path):
    assert load_suppressions(tmp_path / "nope.yaml") == set()


def test_active_suppression_is_loaded(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("- fingerprint: abc123\n  reason: known noise\n", encoding="utf-8")
    assert load_suppressions(p) == {"abc123"}


def test_expired_suppression_is_dropped(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("- fingerprint: abc123\n  expires: 2020-01-01\n", encoding="utf-8")
    assert load_suppressions(p, today=datetime.date(2026, 1, 1)) == set()


def test_filter_removes_suppressed_issues():
    issues = [_issue("keep"), _issue("drop")]
    assert filter_suppressed(issues, {"drop"}) == [issues[0]]
