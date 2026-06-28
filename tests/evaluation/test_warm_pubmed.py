import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "warm_pubmed", REPO / "evaluation" / "scripts" / "warm_pubmed.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_warm_calls_retrieve_for_each_and_tolerates_failure():
    calls = []

    def rf(q):
        calls.append(q)
        if q == "boom":
            raise RuntimeError("ncbi down")
        return (["r1", "r2"], "search query")

    res = mod.warm([("A", "qa"), ("B", "boom"), ("C", "qc")], rf)
    assert calls == ["qa", "boom", "qc"]          # every question attempted, in order
    assert res == [("A", 2, True), ("B", 0, False), ("C", 2, True)]
