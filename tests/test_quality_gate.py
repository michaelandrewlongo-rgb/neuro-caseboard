"""WS-1 — held-out eval set shape + offline quality-regression gate.

All offline and deterministic (no keys, no network). The dataset-shape tests guard the held-out
eval set; the gate tests guard `eval/quality_gate.py` (aggregates the offline quality signals on
the `eval` split and fails below `eval/BASELINE.json`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parent.parent / "eval"


def _load(name):
    return json.loads((EVAL / name).read_text())


# --------------------------------------------------------------------------- dataset shape

def test_eval_set_size_and_breadth():
    cases = _load("cases.json")["cases"]
    assert len(cases) >= 24, f"expected >=24 cases, got {len(cases)}"
    subs = {c["subspecialty"] for c in cases}
    assert len(subs) >= 7, f"expected >=7 subspecialties, got {len(subs)}: {sorted(subs)}"
    for c in cases:
        assert c["must_cover"], f"{c['id']} has empty must_cover"
        assert c["red_flags"], f"{c['id']} has empty red_flags"
        assert c["split"] in {"tune", "eval"}, f"{c['id']} has bad split {c['split']!r}"


def test_split_partition():
    cases = _load("cases.json")["cases"]
    tune = {c["id"] for c in cases if c["split"] == "tune"}
    ev = {c["id"] for c in cases if c["split"] == "eval"}
    assert tune and ev
    assert tune.isdisjoint(ev), "tune/eval splits must be disjoint by id"
    assert len(tune) + len(ev) == len(cases), "every case is tune xor eval"
    frac_eval = len(ev) / len(cases)
    assert 0.55 <= frac_eval <= 0.75, f"eval should be ~2/3, got {frac_eval:.2f}"


def test_dictations_mirror_cases():
    case_ids = {c["id"] for c in _load("cases.json")["cases"]}
    dicts = _load("case_dictations.json")["dictations"]
    dict_ids = [d["id"] for d in dicts]
    assert len(dict_ids) == len(set(dict_ids)), "duplicate dictation ids"
    assert set(dict_ids) == case_ids, (
        f"dictations must mirror cases; "
        f"missing={case_ids - set(dict_ids)} extra={set(dict_ids) - case_ids}"
    )
    required = {"laterality", "level", "location", "pathology", "procedure",
                "surgical_goal", "comorbidities"}
    for d in dicts:
        assert d.get("dictation"), f"{d['id']} has empty dictation"
        gt = d.get("ground_truth", {})
        assert required <= set(gt), f"{d['id']} ground_truth missing {required - set(gt)}"


# --------------------------------------------------------------------------- gate behavior

from eval import quality_gate as qg  # noqa: E402


@pytest.fixture(scope="module")
def eval_metrics():
    """Compute the gate metrics on the eval split once for the whole module (the build is the
    expensive part)."""
    return qg.compute_metrics(qg.load_split("eval"))


def test_gate_reads_only_eval_split():
    all_ids = {c["id"] for c in _load("cases.json")["cases"]}
    eval_ids = {c["id"] for c in _load("cases.json")["cases"] if c["split"] == "eval"}
    tune_ids = all_ids - eval_ids
    data = qg.load_split("eval")
    got = {c["id"] for c in data.cases}
    assert got == eval_ids, "load_split('eval') must return exactly the eval-split cases"
    assert got.isdisjoint(tune_ids), "no tune-split case may leak into the eval gate"
    # dictations + figure cases are likewise filtered to the eval split
    assert {d["id"] for d in data.dictations} <= eval_ids
    assert {c["id"] for c in data.figure_cases} <= eval_ids


def test_gate_deterministic(eval_metrics):
    again = qg.compute_metrics(qg.load_split("eval"))
    assert again == eval_metrics, "compute_metrics must be deterministic/offline (no randomness)"


def test_compare_min_metric_regression_fails():
    base = {"section_coverage_gt": {"value": 1.0, "direction": "min"}}
    ok_pass, _ = qg.compare({"section_coverage_gt": 1.0}, base)
    ok_fail, rows = qg.compare({"section_coverage_gt": 0.5}, base)
    assert ok_pass is True
    assert ok_fail is False
    assert any(r["metric"] == "section_coverage_gt" and r["ok"] is False for r in rows)


def test_compare_max_metric_regression_fails():
    base = {"red_flag_contamination": {"value": 0.0, "direction": "max"}}
    ok_pass, _ = qg.compare({"red_flag_contamination": 0.0}, base)
    ok_fail, _ = qg.compare({"red_flag_contamination": 1.0}, base)
    assert ok_pass is True
    assert ok_fail is False


def test_gate_passes_on_committed_baseline(eval_metrics):
    baseline = qg.load_baseline(qg.DEFAULT_BASELINE)
    # every committed baseline metric is actually produced by compute_metrics
    assert set(baseline) <= set(eval_metrics), (
        f"baseline references unknown metrics: {set(baseline) - set(eval_metrics)}"
    )
    ok, rows = qg.compare(eval_metrics, baseline)
    failing = [r for r in rows if not r["ok"]]
    assert ok, f"gate must pass on the committed baseline; failing: {failing}"
    assert qg.main([]) == 0


def test_gate_fails_when_metric_below_baseline(tmp_path):
    bad = {"section_coverage_gt": {"value": 2.0, "direction": "min"}}  # impossible to reach
    p = tmp_path / "BAD_BASELINE.json"
    p.write_text(json.dumps(bad))
    assert qg.main(["--baseline", str(p)]) == 1


from eval.quality_gate import compute_metrics, load_split, DIRECTIONS


def test_attribution_precision_present_and_perfect_offline():
    m = compute_metrics(load_split("eval"))
    assert "attribution_precision" in m
    assert DIRECTIONS["attribution_precision"] == "min"
    assert m["attribution_precision"] == 1.0
