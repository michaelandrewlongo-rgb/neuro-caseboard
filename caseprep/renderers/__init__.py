"""Pure renderer helpers."""

from __future__ import annotations


def compare_rendered_outputs(
    expected: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    """Return deterministic file-level differences between rendered outputs."""
    issues: list[str] = []
    expected_names = set(expected)
    actual_names = set(actual)

    for filename in sorted(expected_names - actual_names):
        issues.append(f"Missing rendered file {filename}")
    for filename in sorted(actual_names - expected_names):
        issues.append(f"Unexpected rendered file {filename}")
    for filename in sorted(expected_names & actual_names):
        if expected[filename] != actual[filename]:
            issues.append(f"Changed rendered file {filename}")
    return issues


__all__ = [
    "compare_rendered_outputs",
]
