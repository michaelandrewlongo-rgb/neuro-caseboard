"""Schema-validation tests for the run-record ``verification`` property (Task B4).

Guards that ``evaluation/schemas/run-record.schema.json`` declares the optional
``verification`` summary (citation-faithfulness / groundedness) and that its nested
field types are actually constrained. ``verification`` is optional (None on error
rows), so it is intentionally *not* in the schema's ``required`` list.

Skips cleanly when ``jsonschema`` is absent (it ships in the ``.[dev]`` extra),
mirroring ``tests/evaluation/test_failure_ledger.py``.
"""
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = json.loads(
    (_REPO_ROOT / "evaluation" / "schemas" / "run-record.schema.json").read_text(encoding="utf-8")
)

# Type-correct dummy values for every field the schema marks required. Keyed so
# ``_base_record`` can build from the live ``required`` list (read from the schema).
_REQUIRED_DUMMIES = {
    "question_id": "GENERAL-01",
    "question": "What supplies Wernicke's area?",
    "domain": "GENERAL",
    "answer": "The MCA supplies the lateral cerebral cortex [1].",
    "status": "completed",  # must be a member of the status enum
    "attempts": 1,
    "started_at": "2026-06-22T00:00:00Z",
    "completed_at": "2026-06-22T00:00:01Z",
    "latency_seconds": 1.5,
    "run_id": "run-test",
}


def _base_record() -> dict:
    """A minimal run record covering exactly the schema's required fields."""
    required = _SCHEMA["required"]
    missing = [f for f in required if f not in _REQUIRED_DUMMIES]
    assert not missing, f"test dummies missing required schema fields: {missing}"
    return {f: _REQUIRED_DUMMIES[f] for f in required}


def test_base_record_is_valid():
    """The dummy base record must itself satisfy the schema.

    Anchors the negative test below: if the wrong-type case raises, the failure is
    attributable to ``verification`` and not to a malformed base record.
    """
    jsonschema.validate(_base_record(), _SCHEMA)


def test_verification_object_validates():
    rec = _base_record()
    rec["verification"] = {
        "n_cited_claims": 3,
        "n_unsupported": 1,
        "groundedness": 0.6667,
        "unsupported_markers": ["1"],
    }
    jsonschema.validate(rec, _SCHEMA)


def test_verification_null_validates():
    rec = _base_record()
    rec["verification"] = None
    jsonschema.validate(rec, _SCHEMA)


def test_verification_wrong_type_fails():
    rec = _base_record()
    # ``n_cited_claims`` is declared ``integer``; a string must be rejected by the
    # nested subschema even though the top level is ``additionalProperties: true``.
    rec["verification"] = {"n_cited_claims": "x"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(rec, _SCHEMA)
