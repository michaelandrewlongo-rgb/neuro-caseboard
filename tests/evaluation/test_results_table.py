import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_results",
    Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "update_results.py",
)
ur = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ur  # dataclass decorator needs the module registered before exec
_SPEC.loader.exec_module(ur)


def _row(run, change, mean, **kw):
    return ur.Row(run=run, date=kw.get("date", "2026-06-20"), change=change,
                  commit=kw.get("commit", "abc1234"), n=kw.get("n", "66"),
                  mean=mean, grades=kw.get("grades", "0/38/22/6"),
                  unsafe=kw.get("unsafe", "0"), notes=kw.get("notes", ""))


def test_render_marks_baseline_dash_and_computes_delta():
    rows = [_row("base", "baseline", 77.74), _row("run2", "C5 guard", 79.36)]
    md = ur.render_table(rows)
    lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    # header, separator, 2 data rows
    assert "Δ vs base" in lines[0]
    assert "| — |" in lines[2]              # baseline delta is a dash
    assert "+1.62" in lines[3]              # 79.36 - 77.74


def test_render_baseline_first_regardless_of_order():
    rows = [_row("run2", "C5 guard", 79.36), _row("base", "baseline", 77.74)]
    md = ur.render_table(rows)
    data = [ln for ln in md.splitlines() if ln.startswith("|")][2:]
    assert "baseline" in data[0]            # baseline pulled to the top


def test_render_no_baseline_all_delta_dash():
    md = ur.render_table([_row("r", "some change", 80.0)])
    data = [ln for ln in md.splitlines() if ln.startswith("|")][2:]
    assert data[0].count("| — |") >= 1      # delta dash when no baseline row


def test_parse_round_trip():
    rows = [_row("base", "baseline", 77.74), _row("run2", "C5 guard", 79.36, notes="keep")]
    parsed = ur.parse_table(ur.render_table(rows))
    assert [r.run for r in parsed] == ["base", "run2"]
    assert parsed[0].is_baseline and not parsed[1].is_baseline
    assert abs(parsed[1].mean - 79.36) < 1e-9
    assert parsed[1].notes == "keep"
    assert parsed[1].grades == "0/38/22/6"
