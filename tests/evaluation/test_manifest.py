"""Verbatim-fidelity and integrity tests for the benchmark manifest.

Dependency-free (no jsonschema) so it runs under the required CI extra `.[dev]`. This test is part
of the project-loop regression harness: it guards that the 67-question benchmark is never silently
altered between the baseline and the comparison run.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "evaluation" / "inputs" / "contemporary-qs-in-neurosurgery"
MANIFEST = REPO_ROOT / "evaluation" / "inputs" / "benchmark-manifest.jsonl"

EXPECTED_COUNTS = {
    "NIS": 8, "SPINE": 9, "TUMOR": 9, "GENERAL": 11,
    "OPEN-CV": 10, "FUNCTIONAL": 10, "TRAUMA": 10,
}
REQUIRED = ("id", "domain", "source_number", "question", "benchmark_version", "enabled")


def _records() -> list[dict]:
    return [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_manifest_exists():
    assert MANIFEST.exists(), f"missing manifest at {MANIFEST}"


def test_exactly_67_unique_questions():
    records = _records()
    assert len(records) == 67, f"expected 67 records, got {len(records)}"
    ids = [r["id"] for r in records]
    assert len(set(ids)) == 67, "IDs are not unique"


def test_per_section_counts():
    records = _records()
    counts: dict[str, int] = {}
    for r in records:
        prefix = r["id"].rsplit("-", 1)[0]
        counts[prefix] = counts.get(prefix, 0) + 1
    assert counts == EXPECTED_COUNTS, f"section counts mismatch: {counts}"


def test_source_numbers_restart_and_are_contiguous():
    records = _records()
    for prefix, expected in EXPECTED_COUNTS.items():
        nums = sorted(r["source_number"] for r in records if r["id"].rsplit("-", 1)[0] == prefix)
        assert nums == list(range(1, expected + 1)), f"{prefix}: source_number not 1..{expected}: {nums}"


def test_required_fields_and_types():
    for r in _records():
        for field in REQUIRED:
            assert field in r, f"{r.get('id', '?')}: missing field '{field}'"
        assert isinstance(r["enabled"], bool)
        assert isinstance(r["source_number"], int)
        assert isinstance(r["question"], str) and r["question"].strip()


def test_questions_are_verbatim_substrings_of_source():
    """The strongest guard: every manifest question appears unchanged in the preserved source."""
    source_text = SOURCE.read_text(encoding="utf-8")
    for r in _records():
        assert r["question"] in source_text, (
            f"{r['id']}: question text is not a verbatim substring of the source — "
            "normalization must never alter question text"
        )
