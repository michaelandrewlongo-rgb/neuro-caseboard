from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Evidence:
    case_id: str
    detail: str
    before: float | None = None
    after: float | None = None


@dataclass(frozen=True)
class Issue:
    kind: str
    severity: str
    title: str
    evidence: list[Evidence]
    locus: str
    proposed_tier: str
    proposed_fix: str
    fingerprint: str


@dataclass(frozen=True)
class RunArtifacts:
    cases: list[dict]
    boards: dict[str, list[str]]
    baseline: dict
    explorer: dict = field(default_factory=dict)


class Detector(Protocol):
    name: str

    def detect(self, art: RunArtifacts) -> list[Issue]:
        ...
