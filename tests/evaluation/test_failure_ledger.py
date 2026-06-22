"""Tests for build_failure_ledger.defects_for_run_row (run-row verification → defects).

Loaded via importlib (the script is not an importable package), mirroring
tests/evaluation/test_results_summary.py.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATH = _REPO_ROOT / "evaluation" / "scripts" / "build_failure_ledger.py"
_SCHEMA = _REPO_ROOT / "evaluation" / "schemas" / "defect-record.schema.json"


@pytest.fixture(scope="module")
def ledger_module():
    spec = importlib.util.spec_from_file_location("build_failure_ledger", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unsupported_claim_defect_emitted(ledger_module):
    row = {"question_id": "Q1", "answer": "Claim one [1]. Claim two [L2].",
           "verification": {"n_cited_claims": 3, "n_unsupported": 2, "unsupported_markers": ["1", "L2"]}}
    defects = ledger_module.defects_for_run_row(row)
    assert len(defects) == 1
    d = defects[0]
    assert d["category"] == "unsupported_claim"
    assert d["question_id"] == "Q1"
    assert d["probable_layer"] in ("model_synthesis", "citation_rendering")


def test_no_defect_when_grounded(ledger_module):
    assert ledger_module.defects_for_run_row(
        {"question_id": "Q1", "verification": {"n_cited_claims": 2, "n_unsupported": 0}}) == []
    assert ledger_module.defects_for_run_row({"question_id": "Q1"}) == []


def test_layer_entries_present(ledger_module):
    assert ledger_module.LAYER["unsupported_claim"] == (
        "model_synthesis", ["neuro_caseboard/answer_verify.py", "neuro_core/synthesize.py"])
    assert ledger_module.LAYER["citation_claim_mismatch"] == (
        "citation_rendering", ["neuro_caseboard/qa.py"])


def test_emitted_defect_validates_against_schema(ledger_module):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    row = {"question_id": "Q1", "answer": "Claim one [1]. Claim two [L2].",
           "verification": {"n_cited_claims": 3, "n_unsupported": 2, "unsupported_markers": ["1", "L2"]}}
    defects = ledger_module.defects_for_run_row(row)
    assert defects, "expected at least one defect to validate"
    for d in defects:
        jsonschema.validate(d, schema)
