"""Remembered operative preferences — the memory half of the surgeon-in-the-loop.

Surgeon marks distil into reusable, case-INDEPENDENT ``Preference`` rules keyed by ``profile``.
Re-encountering the same (profile, action, pattern) bumps ``weight`` and records the source case
(provenance), so a repeatedly-asserted heuristic is reinforced — which the conservative guardrail
in ``apply_preferences`` uses to gate removal. Pure, stdlib-only, offline.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from neuro_caseboard.feedback import CaseFeedback

ACTIONS = ("suppress", "elevate", "add")
_MARK_ACTION = {"wrong": "suppress", "important": "elevate", "missing": "add"}
_STOP = {"the", "a", "an", "of", "and", "or", "to", "for", "in", "on", "at", "is", "are",
         "with", "this", "that", "case", "patient", "confirm", "identify"}


def _key_terms(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return " ".join(sorted({w for w in words if len(w) > 2 and w not in _STOP}))


def _default_why(action: str) -> str:
    return {"suppress": "Surgeon marked this content as wrong / not applicable.",
            "elevate": "Surgeon flagged this as critical for this kind of case.",
            "add": "Surgeon noted this consideration was missing."}.get(action, "")


def default_store_path() -> Path:
    """The server-side preferences store. Override via CASEBOARD_PREFS_STORE; default repo-root file."""
    return Path(os.environ.get("CASEBOARD_PREFS_STORE", "operative-preferences.json"))


@dataclass
class Preference:
    profile: str
    action: str
    pattern: str
    text: str = ""
    why: str = ""
    target_file: str = "04-operative-plan.md"
    section_key: str = "critical_steps"
    compiler_slot: str = "Critical Steps"
    weight: int = 1
    sources: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}, got {self.action!r}")


def distill(feedback: CaseFeedback, existing: list[Preference] | None = None) -> list[Preference]:
    prefs = [Preference(**asdict(p)) for p in (existing or [])]
    index = {(p.profile, p.action, p.pattern): p for p in prefs}
    for item in feedback.items:
        action = _MARK_ACTION[item.mark]
        pattern = _key_terms(item.text)
        if not pattern:
            continue
        key = (feedback.profile, action, pattern)
        if key in index:
            p = index[key]
            p.weight += 1
            if feedback.topic and feedback.topic not in p.sources:
                p.sources.append(feedback.topic)
            continue
        p = Preference(profile=feedback.profile, action=action, pattern=pattern,
                       text=item.text, why=item.note or _default_why(action),
                       target_file=item.target_file, section_key=item.section_key,
                       compiler_slot=item.compiler_slot,
                       sources=[feedback.topic] if feedback.topic else [])
        prefs.append(p)
        index[key] = p
    return prefs


def save_preferences(prefs: list[Preference], path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(x) for x in prefs], indent=2), encoding="utf-8")
    return p


def load_preferences(path) -> list[Preference]:
    p = Path(path)
    if not p.exists():
        return []
    return [Preference(**d) for d in json.loads(p.read_text(encoding="utf-8"))]
