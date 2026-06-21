import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_results",
    Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "update_results.py",
)
ur = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ur  # dataclass decorator needs the module registered before exec
_SPEC.loader.exec_module(ur)


def _write_summary(d: Path, mean=77.74, ng=0):
    (d / "s-summary.json").write_text(json.dumps({
        "overall_score": {"n": 66, "mean": mean},
        "grade_distribution": {"A": 0, "B": 38, "C": 22, "D": 6, "F": 0, "Not gradable": ng},
        "unsafe_answer_count": 0,
    }))
    (d / "run-config.json").write_text(json.dumps({
        "application_commit": "28a6e30ab5b2697acc4dafe0a46824c8c3c42e6a",
        "working_tree_dirty": True,
        "created_at": "2026-06-20T13:47:23.871700+00:00",
    }))


def test_row_from_summary_reads_metrics_and_runconfig(tmp_path):
    _write_summary(tmp_path)
    row = ur.row_from_summary(tmp_path / "s-summary.json", run="baseline-x",
                              label="baseline", baseline=True)
    assert row.is_baseline
    assert abs(row.mean - 77.74) < 1e-9
    assert row.n == "66"
    assert row.grades == "0/38/22/6"
    assert row.unsafe == "0"
    assert row.commit == "28a6e30 dirty"        # short sha + dirty marker
    assert row.date == "2026-06-20"


def test_row_from_summary_notes_not_gradable(tmp_path):
    _write_summary(tmp_path, ng=1)
    row = ur.row_from_summary(tmp_path / "s-summary.json", run="r", label="chg")
    assert row.change == "chg"
    assert "1 not-gradable" in row.notes


def test_cli_summary_writes_results(tmp_path, monkeypatch):
    _write_summary(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evaluation").mkdir()
    rc = ur.main(["--summary", str(tmp_path / "s-summary.json"),
                  "--run", "baseline-x", "--label", "baseline", "--baseline"])
    assert rc == 0
    text = (tmp_path / "evaluation" / "RESULTS.md").read_text()
    assert "| baseline-x |" in text and "77.74" in text
