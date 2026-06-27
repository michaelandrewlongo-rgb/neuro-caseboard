import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
M21 = REPO / "evaluation" / "inputs" / "bakeoff-21.manifest.jsonl"
M67 = REPO / "evaluation" / "inputs" / "benchmark-manifest.jsonl"
HARD = {"NIS-02", "OPEN-CV-04", "OPEN-CV-07", "TUMOR-01", "TUMOR-05",
        "SPINE-01", "SPINE-06", "FUNCTIONAL-02", "TRAUMA-02", "GENERAL-01"}


def _rows(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_manifest_has_21_unique_enabled_rows():
    rows = _rows(M21)
    assert len(rows) == 21
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 21
    assert all(r["enabled"] for r in rows)
    for r in rows:
        assert r["question"].strip()
        for f in ("id", "domain", "question", "benchmark_version", "enabled"):
            assert f in r


def test_hard_qids_are_byte_identical_to_frozen_benchmark():
    committed = {r["id"]: r["question"] for r in _rows(M67)}
    got = {r["id"]: r["question"] for r in _rows(M21)}
    assert HARD.issubset(set(got))
    for qid in HARD:
        assert got[qid] == committed[qid], f"{qid} text drifted from the frozen benchmark"
