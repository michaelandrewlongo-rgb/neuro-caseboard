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


def _make_ab(tmp_path):
    run = tmp_path / "myab-20260620-2210"
    (run / "grading").mkdir(parents=True)
    (run / "ab-out").mkdir()
    (run / "grading" / "keymap.json").write_text(json.dumps(
        {"arms": ["recent", "youmans"], "questions": {}}))
    (run / "run-config.json").write_text(json.dumps(
        {"application_commit": "deadbeef1234", "working_tree_dirty": False,
         "created_at": "2026-06-20T22:10:00+00:00"}))

    def _grades(arm, scores, letters):
        lines = [json.dumps({"question_id": f"Q{i}", "score": s, "letter_grade": g})
                 for i, (s, g) in enumerate(zip(scores, letters))]
        (run / "ab-out" / f"{arm}-grades.jsonl").write_text("\n".join(lines) + "\n")

    _grades("recent", [80, 90], ["B", "A"])     # mean 85.0
    _grades("youmans", [70, 80], ["C", "B"])    # mean 75.0
    return run


def test_rows_from_ab_one_row_per_arm(tmp_path):
    run = _make_ab(tmp_path)
    rows = ur.rows_from_ab(run, label="3-arm corpus")
    by_run = {r.run: r for r in rows}
    assert set(by_run) == {f"{run.name} · recent", f"{run.name} · youmans"}
    recent = by_run[f"{run.name} · recent"]
    assert abs(recent.mean - 85.0) < 1e-9
    assert recent.n == "2"
    assert recent.grades == "1/1/0/0"            # A=1,B=1,C=0,D=0
    assert recent.unsafe == "—"                  # no unsafe field in A/B grades
    assert recent.change == "3-arm corpus (recent)"
    assert recent.commit == "deadbee"            # clean tree -> no dirty marker
    assert recent.date == "2026-06-20"


def test_cli_ab_writes_two_rows(tmp_path, monkeypatch):
    run = _make_ab(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evaluation").mkdir()
    rc = ur.main(["--ab", str(run), "--label", "3-arm corpus"])
    assert rc == 0
    text = (tmp_path / "evaluation" / "RESULTS.md").read_text()
    assert f"| {run.name} · recent |" in text
    assert f"| {run.name} · youmans |" in text
