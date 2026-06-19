"""Surgeon feedback on a generated board — the input half of the surgeon-in-the-loop.

Marks live on an axis DISTINCT from the evidence/status axis in model.py: ``wrong`` (incorrect
or not applicable to THIS case), ``missing`` (an important consideration the board omitted),
``important`` (critical for THIS case → elevate). Persisted as JSON so preferences.py can distil
them into reusable, profile-keyed operative heuristics. Stdlib-only; decoupled from caseprep.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MARKS = ("wrong", "missing", "important")

# Board section heading -> compiler target_file (3-section build path). Lets the web send a human
# section name for a "missing" add and have it land in the right board section.
_HEADING_TARGET = {
    "anatomy at risk": "03-anatomy-at-risk.md",
    "operative plan": "04-operative-plan.md",
    "risk and rescue": "05-risk-and-rescue.md",
}


def target_file_for_heading(heading: str) -> str:
    return _HEADING_TARGET.get((heading or "").strip().lower(), "04-operative-plan.md")


@dataclass
class FeedbackItem:
    mark: str
    text: str
    target_file: str = "04-operative-plan.md"
    section_key: str = "critical_steps"
    compiler_slot: str = "Critical Steps"
    note: str = ""

    def __post_init__(self) -> None:
        if self.mark not in MARKS:
            raise ValueError(f"mark must be one of {MARKS}, got {self.mark!r}")


@dataclass
class CaseFeedback:
    topic: str
    profile: str = ""
    items: list[FeedbackItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"topic": self.topic, "profile": self.profile,
                "items": [asdict(i) for i in self.items]}

    @classmethod
    def from_dict(cls, d: dict) -> "CaseFeedback":
        return cls(topic=d.get("topic", ""), profile=d.get("profile", ""),
                   items=[FeedbackItem(**i) for i in d.get("items", [])])


def save_feedback(fb: CaseFeedback, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fb.to_dict(), indent=2), encoding="utf-8")
    return p


def load_feedback(path) -> CaseFeedback:
    return CaseFeedback.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
