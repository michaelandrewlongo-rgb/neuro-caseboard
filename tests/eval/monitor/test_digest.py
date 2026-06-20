from __future__ import annotations

from eval.monitor.contracts import Evidence, Issue
from eval.monitor.digest import render_digest


def test_empty_digest_says_no_issues():
    out = render_digest([])
    assert "No new issues" in out


def test_digest_lists_issue_sorted_by_severity():
    low = Issue(kind="coverage_drop", severity="low", title="low one", evidence=[],
                locus="author", proposed_tier="knob-only", proposed_fix="f", fingerprint="l1")
    high = Issue(kind="coverage_drop", severity="high", title="high one",
                 evidence=[Evidence("c1", "missing X", before=0.9, after=0.4)],
                 locus="author", proposed_tier="knob-only", proposed_fix="f", fingerprint="h1")
    out = render_digest([low, high])
    assert out.index("high one") < out.index("low one")   # high sorts first
    assert "missing X" in out
    assert "`h1`" in out
