#!/usr/bin/env python3
"""Validate the benchmark manifest against the source and schema.

Checks (exit non-zero on any failure):
  1. Exactly 67 records, 67 unique IDs.
  2. Per-section counts match the expected ID scheme.
  3. Every ``question`` is a verbatim substring of the source file (normalization altered nothing).
  4. Every record carries the required fields with the right primitive types.
  5. If ``jsonschema`` is importable, each record also validates against
     ``evaluation/schemas/benchmark-manifest.schema.json``.

Run:  python3 evaluation/scripts/validate_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "evaluation" / "inputs" / "contemporary-qs-in-neurosurgery"
MANIFEST = REPO_ROOT / "evaluation" / "inputs" / "benchmark-manifest.jsonl"
SCHEMA = REPO_ROOT / "evaluation" / "schemas" / "benchmark-manifest.schema.json"

EXPECTED_COUNTS = {
    "NIS": 8, "SPINE": 9, "TUMOR": 9, "GENERAL": 11,
    "OPEN-CV": 10, "FUNCTIONAL": 10, "TRAUMA": 10,
}
TOTAL = 67
REQUIRED = ("id", "domain", "source_number", "question", "benchmark_version", "enabled")


def load_records() -> list[dict]:
    return [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate(records: list[dict], source_text: str) -> list[str]:
    errors: list[str] = []

    if len(records) != TOTAL:
        errors.append(f"expected {TOTAL} records, found {len(records)}")

    ids = [r.get("id") for r in records]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        errors.append(f"duplicate IDs: {dupes}")

    counts: dict[str, int] = {}
    for r in records:
        rid = r.get("id", "")
        prefix = rid.rsplit("-", 1)[0] if rid else ""
        counts[prefix] = counts.get(prefix, 0) + 1
    for prefix, expected in EXPECTED_COUNTS.items():
        if counts.get(prefix, 0) != expected:
            errors.append(f"{prefix}: expected {expected}, got {counts.get(prefix, 0)}")
    for prefix in counts:
        if prefix not in EXPECTED_COUNTS:
            errors.append(f"unexpected ID prefix: {prefix}")

    for r in records:
        for field in REQUIRED:
            if field not in r:
                errors.append(f"{r.get('id', '?')}: missing field '{field}'")
        q = r.get("question", "")
        # verbatim fidelity: the question text must appear unchanged in the source
        if q and q not in source_text:
            errors.append(f"{r.get('id', '?')}: question not a verbatim substring of source")
        if not isinstance(r.get("enabled"), bool):
            errors.append(f"{r.get('id', '?')}: 'enabled' must be boolean")
        if not isinstance(r.get("source_number"), int):
            errors.append(f"{r.get('id', '?')}: 'source_number' must be integer")

    # Optional: full JSON Schema validation when jsonschema is available.
    try:
        import jsonschema  # type: ignore

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for r in records:
            try:
                jsonschema.validate(r, schema)
            except jsonschema.ValidationError as exc:  # pragma: no cover
                errors.append(f"{r.get('id', '?')}: schema violation: {exc.message}")
    except ModuleNotFoundError:
        pass

    return errors


def main() -> int:
    records = load_records()
    source_text = SOURCE.read_text(encoding="utf-8")
    errors = validate(records, source_text)
    if errors:
        print("MANIFEST VALIDATION FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"manifest OK: {len(records)} questions, verbatim-verified against source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
