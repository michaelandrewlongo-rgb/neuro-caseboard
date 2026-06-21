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


def _row(run, change, mean, notes=""):
    return ur.Row(run=run, date="2026-06-20", change=change, commit="abc1234",
                  n="66", mean=mean, grades="0/38/22/6", unsafe="0", notes=notes)


def test_creates_file_with_preamble_and_row(tmp_path):
    p = tmp_path / "RESULTS.md"
    ur.write_results(p, [_row("base", "baseline", 77.74)])
    text = p.read_text()
    assert text.startswith("# 67-Question Benchmark")   # preamble present
    assert "Unsafe" in text and "must stay" in text     # explains itself
    assert "| base |" in text
    assert "update_results.py" in text                  # footer usage block


def test_upsert_is_idempotent(tmp_path):
    p = tmp_path / "RESULTS.md"
    ur.write_results(p, [_row("base", "baseline", 77.74)])
    ur.write_results(p, [_row("run2", "C5 guard", 79.36)])
    ur.write_results(p, [_row("run2", "C5 guard", 81.00, notes="rescored")])  # same run id
    text = p.read_text()
    assert text.count("| run2 |") == 1                  # updated, not duplicated
    assert "81.00" in text and "79.36" not in text
    assert "+3.26" in text                              # 81.00 - 77.74, Δ recomputed


def test_preamble_preserved_across_upserts(tmp_path):
    p = tmp_path / "RESULTS.md"
    ur.write_results(p, [_row("base", "baseline", 77.74)])
    first = p.read_text().split("| Run |")[0]
    ur.write_results(p, [_row("run2", "C5 guard", 79.36)])
    second = p.read_text().split("| Run |")[0]
    assert first == second                              # preamble byte-identical
