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

from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest

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


def _card_signature(card: QuestionCard) -> str:
    return _key_terms(f"{card.question} {card.why_it_matters}")


def _matches(pattern: str, card: QuestionCard) -> bool:
    pat = set(pattern.split())
    return bool(pat) and pat <= set(_card_signature(card).split())


def apply_preferences(manifest: QuestionManifest, profile: str,
                      prefs: list[Preference] | None) -> QuestionManifest:
    """Re-express stored preferences against a fresh manifest. Profile-scoped. Conservative:
    a ``suppress`` pref with weight>=2 REMOVES matching cards; weight<2 only DE-EMPHASIZES them
    (stable-move to the END of the card list — content retained; the compiler pins section order, so a
    de-emphasized card simply renders last within its own section). ``add`` injects when absent;
    ``elevate`` moves matching cards to the front. Order: suppress -> add -> elevate. New frozen
    manifest; input unchanged."""
    if not prefs:
        return manifest
    active = [p for p in prefs if p.profile in ("", profile)]
    if not active:
        return manifest
    cards = list(manifest.cards)

    remove = [p.pattern for p in active if p.action == "suppress" and p.weight >= 2]
    if remove:
        cards = [c for c in cards if not any(_matches(pat, c) for pat in remove)]

    deemph = [p.pattern for p in active if p.action == "suppress" and p.weight < 2]
    if deemph:
        def _d(c): return any(_matches(pat, c) for pat in deemph)
        cards = [c for c in cards if not _d(c)] + [c for c in cards if _d(c)]

    for p in [p for p in active if p.action == "add"]:
        if not any(_matches(p.pattern, c) for c in cards):
            cards.append(QuestionCard(target_file=p.target_file, section_key=p.section_key,
                                      question=p.text, why_it_matters=p.why or _default_why("add"),
                                      compiler_slot=p.compiler_slot))

    elev = [p.pattern for p in active if p.action == "elevate"]
    if elev:
        def _e(c): return any(_matches(pat, c) for pat in elev)
        cards = [c for c in cards if _e(c)] + [c for c in cards if not _e(c)]

    return QuestionManifest(procedure_family=getattr(manifest, "procedure_family", "generic"), cards=cards)

