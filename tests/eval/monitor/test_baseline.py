from __future__ import annotations

import json

from eval.monitor.baseline import is_regression, load_baseline


def test_absolute_floor_breach_is_regression():
    assert is_regression(None, 0.50, rel_margin=0.05, abs_floor=0.70) is True


def test_healthy_first_run_is_not_a_regression():
    assert is_regression(None, 0.90, rel_margin=0.05, abs_floor=0.70) is False


def test_relative_drop_beyond_margin_is_regression():
    assert is_regression(0.90, 0.80, rel_margin=0.05, abs_floor=0.70) is True


def test_small_dip_within_margin_is_not_a_regression():
    assert is_regression(0.90, 0.88, rel_margin=0.05, abs_floor=0.70) is False


def test_load_baseline_missing_returns_empty(tmp_path):
    assert load_baseline(tmp_path / "nope.json") == {}


def test_load_baseline_reads_json(tmp_path):
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps({"c1": {"coverage": 0.9}}), encoding="utf-8")
    assert load_baseline(p) == {"c1": {"coverage": 0.9}}
