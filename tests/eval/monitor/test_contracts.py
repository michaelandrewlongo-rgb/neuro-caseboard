from __future__ import annotations

from eval.monitor.contracts import Evidence, Issue, RunArtifacts


def test_issue_and_evidence_construct():
    ev = Evidence(case_id="c1", detail="missing X", before=0.9, after=0.5)
    iss = Issue(
        kind="coverage_drop", severity="high", title="c1 dropped",
        evidence=[ev], locus="author", proposed_tier="knob-only",
        proposed_fix="tweak prompt", fingerprint="abc123",
    )
    assert iss.evidence[0].after == 0.5
    assert iss.fingerprint == "abc123"


def test_runartifacts_defaults_explorer_empty():
    art = RunArtifacts(cases=[{"id": "c1"}], boards={"c1": ["board"]}, baseline={})
    assert art.explorer == {}
    assert art.boards["c1"] == ["board"]
