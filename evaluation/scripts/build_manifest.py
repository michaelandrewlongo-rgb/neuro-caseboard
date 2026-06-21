#!/usr/bin/env python3
"""Build the machine-readable benchmark manifest from the verbatim source file.

Deterministic: parses ``evaluation/inputs/contemporary-qs-in-neurosurgery`` (preserved byte-for-byte
from the user-supplied original) and emits one JSONL record per question with a stable ID. Question
text is copied verbatim from the source line — never paraphrased — so the validator can assert each
manifest question is a substring of the source.

Stable IDs are assigned per section because the source numbering restarts each section:

    NIS-01..08  SPINE-01..09  TUMOR-01..09  GENERAL-01..11
    OPEN-CV-01..10  FUNCTIONAL-01..10  TRAUMA-01..10   (67 total)

Run:  python3 evaluation/scripts/build_manifest.py
Writes:  evaluation/inputs/benchmark-manifest.jsonl
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "evaluation" / "inputs" / "contemporary-qs-in-neurosurgery"
OUT = REPO_ROOT / "evaluation" / "inputs" / "benchmark-manifest.jsonl"

# Section heading (verbatim in source) -> (domain, id_prefix, expected_count)
SECTIONS: dict[str, tuple[str, str, int]] = {
    "Neurointerventional Surgery": ("Neurointerventional Surgery", "NIS", 8),
    "Spine Surgery": ("Spine Surgery", "SPINE", 9),
    "Brain Tumor Surgery": ("Brain Tumor Surgery", "TUMOR", 9),
    "General Neurosurgery": ("General Neurosurgery", "GENERAL", 11),
    "Open Cerebrovascular Surgery": ("Open Cerebrovascular Surgery", "OPEN-CV", 10),
    "Functional Neurosurgery": ("Functional Neurosurgery", "FUNCTIONAL", 10),
    "Trauma Neurosurgery": ("Trauma Neurosurgery", "TRAUMA", 10),
}

_H2 = re.compile(r"^##\s+(.*\S)\s*$")
_NUM = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")


def parse_source(text: str) -> list[dict]:
    """Return ordered question records parsed verbatim from the source markdown."""
    records: list[dict] = []
    current_section: str | None = None
    for raw in text.splitlines():
        h2 = _H2.match(raw)
        if h2:
            current_section = h2.group(1)
            continue
        num = _NUM.match(raw)
        if num and current_section in SECTIONS:
            domain, prefix, _count = SECTIONS[current_section]
            source_number = int(num.group(1))
            question = num.group(2)  # verbatim, single source line
            records.append(
                {
                    "domain": domain,
                    "prefix": prefix,
                    "source_number": source_number,
                    "question": question,
                }
            )
    return records


def build() -> list[dict]:
    text = SOURCE.read_text(encoding="utf-8")
    version = "contemporary-qs-in-neurosurgery:" + hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:12]

    parsed = parse_source(text)

    # Group by section in first-seen order; assign zero-padded stable IDs.
    out: list[dict] = []
    per_prefix_counter: dict[str, int] = {}
    for rec in parsed:
        prefix = rec["prefix"]
        per_prefix_counter[prefix] = per_prefix_counter.get(prefix, 0) + 1
        n = per_prefix_counter[prefix]
        out.append(
            {
                "id": f"{prefix}-{n:02d}",
                "domain": rec["domain"],
                "source_number": rec["source_number"],
                "question": rec["question"],
                "benchmark_version": version,
                "enabled": True,
            }
        )

    # Integrity checks (fail loudly rather than emit a wrong manifest).
    assert len(out) == 67, f"expected 67 questions, parsed {len(out)}"
    for section, (_domain, prefix, expected) in SECTIONS.items():
        got = per_prefix_counter.get(prefix, 0)
        assert got == expected, f"{section}: expected {expected}, got {got}"
    # source_number must restart at 1 and be contiguous within each prefix
    for section, (_domain, prefix, expected) in SECTIONS.items():
        nums = [r["source_number"] for r in out if r["id"].startswith(prefix + "-")]
        assert nums == list(range(1, expected + 1)), f"{section}: source_number not 1..{expected}: {nums}"
    return out


def main() -> None:
    records = build()
    with OUT.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} records -> {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
