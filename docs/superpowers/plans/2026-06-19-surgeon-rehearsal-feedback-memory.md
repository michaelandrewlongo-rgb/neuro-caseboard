# Surgeon-in-the-Loop: Board Feedback + Remembered Operative Preferences — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a surgeon mark a generated case board as wrong / missing / important, and have the system distil those marks into reusable, case-independent operative preferences that update the next board it generates.

**Architecture:** Two new stdlib-only modules — `feedback.py` (capture marks on a board) and `preferences.py` (distil marks into a persisted `Preference` set and re-express that set against a fresh `QuestionManifest`). One optional `prefs=None` parameter is threaded through the existing pipeline (`build_manifest` → `build_dossier` / `build_case_dossier`) and applied immediately **after** `prune_offtarget`, so it benefits both the legacy free-text `build` path and the structured-case `case` path. A new `caseboard feedback` CLI records marks into the store; a `--prefs` flag on `build`/`case` applies it. Default (`prefs=None`) is a no-op, so all existing behavior is byte-identical.

**Tech Stack:** Python 3.10+, stdlib `dataclasses`/`json`/`re`; the vendored `caseprep.explorer.question_manifest` (`QuestionCard`, `QuestionManifest`); pytest.

## Global Constraints

- **New modules are stdlib-only and fully offline** — no network, no GPU, no torch/sentence-transformers. Tests inject fakes; never call a live LLM.
- **Default path unchanged:** `prefs=None`/absent must be a no-op. The existing scoped harness (92 tests) MUST stay green.
- **Feedback axis is DISTINCT** from the evidence/`status` axis in `model.py` (`supported`/`verify`). Surgeon marks are ground truth; never conflate them with the machine-derived audit status.
- **`QuestionCard` and `QuestionManifest` are frozen** — construct new objects; never mutate in place.
- **caseprep is vendored in-tree** — import `from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest`. Do NOT install an external caseprep.
- **New tests live under `tests/rehearsal/`** (the package already exists). Run the scoped harness with the worktree venv; never the full suite, never `-n`/pytest-xdist.
- Harness (run from the worktree root):
  `.loopvenv/bin/python -m pytest -p no:cacheprovider -q tests/test_pipeline.py tests/test_compile.py tests/test_render_md.py tests/test_board_view.py tests/test_topic_extract.py tests/rehearsal`

---

## File Structure

- `neuro_caseboard/feedback.py` (**create**) — `MARKS`, `FeedbackItem`, `CaseFeedback`, `save_feedback`, `load_feedback`. The board-marking shape + JSON persistence.
- `neuro_caseboard/preferences.py` (**create**) — `ACTIONS`, `Preference`, `_key_terms`, `distill`, `_matches`, `apply_preferences`, `save_preferences`, `load_preferences`. The memory: distil marks → preferences, and re-express them against a manifest.
- `neuro_caseboard/pipeline.py` (**modify**) — add optional `prefs=None` to `build_manifest`, `build_dossier`, `build_case_dossier`, `generate`, `generate_case`; apply after `prune_offtarget`.
- `neuro_caseboard/cli.py` (**modify**) — add the `feedback` subcommand; add `--prefs` to `build` and `case`.
- `tests/rehearsal/test_feedback.py`, `tests/rehearsal/test_preferences_distill.py`, `tests/rehearsal/test_preferences_apply.py`, `tests/rehearsal/test_pipeline_prefs.py`, `tests/rehearsal/test_cli_feedback.py`, `tests/rehearsal/test_loop_end_to_end.py` (**create**).
- `docs/runbooks/2026-06-19-surgeon-in-the-loop.md` (**create**) — the operator runbook for the loop.

---

### Task 1: Feedback model + JSON persistence

**Files:**
- Create: `neuro_caseboard/feedback.py`
- Test: `tests/rehearsal/test_feedback.py`

**Interfaces:**
- Produces: `MARKS: tuple[str,...]`; `FeedbackItem(mark, text, target_file="04-operative-plan.md", section_key="critical_steps", compiler_slot="Critical Steps", note="")`; `CaseFeedback(topic, profile="", items=[])` with `.to_dict()` / `.from_dict(d)`; `save_feedback(fb, path)->Path`; `load_feedback(path)->CaseFeedback`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_feedback.py
"""Feedback model + JSON round-trip (surgeon-in-the-loop, input half)."""
import pytest

from neuro_caseboard.feedback import (
    MARKS, FeedbackItem, CaseFeedback, save_feedback, load_feedback,
)


def test_marks_are_the_three_axis_values():
    assert set(MARKS) == {"wrong", "missing", "important"}


def test_feedback_item_rejects_unknown_mark():
    with pytest.raises(ValueError):
        FeedbackItem(mark="bogus", text="x")


def test_casefeedback_json_round_trip(tmp_path):
    fb = CaseFeedback(topic="C5-6 corpectomy", profile="spine", items=[
        FeedbackItem(mark="important", text="Vertebral artery course at C1-2",
                     target_file="03-anatomy-at-risk.md"),
        FeedbackItem(mark="wrong", text="Generic positioning checklist"),
        FeedbackItem(mark="missing", text="Confirm fusion construct plan",
                     target_file="04-operative-plan.md", note="I always fuse these"),
    ])
    p = save_feedback(fb, tmp_path / "marks.json")
    assert p.exists()
    back = load_feedback(p)
    assert back == fb
    assert [i.mark for i in back.items] == ["important", "wrong", "missing"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_feedback.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.feedback'`

- [ ] **Step 3: Write minimal implementation**

```python
# neuro_caseboard/feedback.py
"""Surgeon feedback on a generated case board — the input half of the surgeon-in-the-loop.

A board is a Dossier of Claims. After reading it the surgeon marks items along a feedback
axis DISTINCT from the evidence/status axis in ``model.py``: ``wrong`` (incorrect or not
applicable to THIS case), ``missing`` (an important consideration the board omitted), and
``important`` (a claim that is critical for THIS case and should be elevated). The marks are
captured as a ``CaseFeedback`` and persisted as JSON so ``preferences.py`` can distil them
into reusable, case-independent operative heuristics.

Stdlib-only and decoupled from caseprep — an intake/feedback shape, like ``model.py`` and
``case_context.py``.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Feedback axis (surgeon-supplied ground truth). DISTINCT from the machine-derived evidence
# ``status`` axis (supported/verify) in model.py.
MARKS = ("wrong", "missing", "important")


@dataclass
class FeedbackItem:
    """One surgeon mark on the board."""

    mark: str                                    # one of MARKS
    text: str                                    # marked claim (wrong/important) or the missing consideration
    target_file: str = "04-operative-plan.md"    # which board section the item belongs to
    section_key: str = "critical_steps"          # slot for an added (missing) consideration
    compiler_slot: str = "Critical Steps"        # rendered heading for an added consideration
    note: str = ""                               # surgeon's free-text rationale

    def __post_init__(self) -> None:
        if self.mark not in MARKS:
            raise ValueError(f"mark must be one of {MARKS}, got {self.mark!r}")


@dataclass
class CaseFeedback:
    """All marks the surgeon made on one board, plus the case keys to attribute them."""

    topic: str                                   # the board's topic / case.to_topic()
    profile: str = ""                            # spine|skull_base|vascular|"" (classify_profile)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_feedback.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/feedback.py tests/rehearsal/test_feedback.py
git commit -m "feat(rehearsal): surgeon board-feedback model + JSON persistence"
```

---

### Task 2: Preference model + distillation

**Files:**
- Create: `neuro_caseboard/preferences.py`
- Test: `tests/rehearsal/test_preferences_distill.py`

**Interfaces:**
- Consumes: `CaseFeedback`, `FeedbackItem` from Task 1.
- Produces: `ACTIONS`; `_key_terms(text)->str`; `Preference(profile, action, pattern, text="", why="", target_file="04-operative-plan.md", section_key="critical_steps", compiler_slot="Critical Steps", weight=1, sources=[])`; `distill(feedback, existing=None)->list[Preference]`; `save_preferences(prefs, path)->Path`; `load_preferences(path)->list[Preference]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_preferences_distill.py
"""Distil surgeon marks into reusable, reinforced operative preferences."""
from neuro_caseboard.feedback import CaseFeedback, FeedbackItem
from neuro_caseboard.preferences import (
    Preference, distill, save_preferences, load_preferences, _key_terms,
)


def _fb(topic, *items):
    return CaseFeedback(topic=topic, profile="spine", items=list(items))


def test_marks_map_to_actions():
    fb = _fb("C5-6 corpectomy",
             FeedbackItem(mark="wrong", text="Generic positioning checklist"),
             FeedbackItem(mark="important", text="Vertebral artery course"),
             FeedbackItem(mark="missing", text="Confirm fusion construct plan"))
    prefs = distill(fb)
    by_action = {p.action for p in prefs}
    assert by_action == {"suppress", "elevate", "add"}
    assert all(p.profile == "spine" for p in prefs)
    add = next(p for p in prefs if p.action == "add")
    assert add.text == "Confirm fusion construct plan"


def test_distill_reinforces_repeat_across_cases():
    fb1 = _fb("C5-6 corpectomy",
              FeedbackItem(mark="important", text="Vertebral artery course"))
    fb2 = _fb("C1-2 schwannoma",
              FeedbackItem(mark="important", text="course of the vertebral artery"))  # same key terms
    prefs = distill(fb2, distill(fb1))
    assert len(prefs) == 1                      # merged, not duplicated
    assert prefs[0].weight == 2
    assert set(prefs[0].sources) == {"C5-6 corpectomy", "C1-2 schwannoma"}


def test_key_terms_is_order_independent_and_drops_stopwords():
    assert _key_terms("Vertebral artery course") == _key_terms("course of the artery, vertebral")


def test_preferences_json_round_trip(tmp_path):
    prefs = distill(_fb("t", FeedbackItem(mark="wrong", text="Generic positioning checklist")))
    p = save_preferences(prefs, tmp_path / "prefs.json")
    assert load_preferences(p) == prefs
    assert load_preferences(tmp_path / "absent.json") == []     # missing store -> empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_distill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.preferences'`

- [ ] **Step 3: Write minimal implementation**

```python
# neuro_caseboard/preferences.py
"""Remembered operative preferences — the memory half of the surgeon-in-the-loop.

Surgeon feedback (``feedback.py``) on individual boards is distilled into reusable,
case-INDEPENDENT operative ``Preference`` rules keyed by case ``profile`` (spine /
skull_base / vascular / "" = any). A preference says, for its profile:
  - ``suppress``: drop board cards matching a text pattern (from a ``wrong`` mark),
  - ``elevate``: raise matching cards to the top of their section (from an ``important`` mark),
  - ``add``: inject a consideration the surgeon said was ``missing``.
Re-encountering the same (profile, action, pattern) bumps ``weight`` and records the source
case (provenance), so a heuristic the surgeon keeps asserting gets reinforced.

``apply_preferences`` (Task 3) re-expresses a stored set against a fresh manifest — how a later
board "remembers" earlier feedback. Pure, stdlib-only, offline.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from neuro_caseboard.feedback import CaseFeedback

ACTIONS = ("suppress", "elevate", "add")

# feedback mark -> preference action
_MARK_ACTION = {"wrong": "suppress", "important": "elevate", "missing": "add"}

_STOP = {"the", "a", "an", "of", "and", "or", "to", "for", "in", "on", "at", "is", "are",
         "with", "this", "that", "case", "patient", "confirm", "identify"}


def _key_terms(text: str) -> str:
    """A normalized matching signature: lowercased content words >2 chars, deduped, sorted.

    Sorting makes it order-independent, so the same heuristic dictated two different ways
    merges into one preference and matches cards regardless of word order."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return " ".join(sorted({w for w in words if len(w) > 2 and w not in _STOP}))


def _default_why(action: str) -> str:
    return {"suppress": "Surgeon marked this content as wrong / not applicable.",
            "elevate": "Surgeon flagged this as critical for this kind of case.",
            "add": "Surgeon noted this consideration was missing."}.get(action, "")


@dataclass
class Preference:
    profile: str                                 # "" = any profile
    action: str                                  # one of ACTIONS
    pattern: str                                 # normalized key-terms signature
    text: str = ""                               # consideration to inject (add) / source claim
    why: str = ""                                # rationale shown on an added card
    target_file: str = "04-operative-plan.md"    # add: which section
    section_key: str = "critical_steps"
    compiler_slot: str = "Critical Steps"
    weight: int = 1                              # reinforcement count
    sources: list[str] = field(default_factory=list)   # topics that produced/confirmed it

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}, got {self.action!r}")


def distill(feedback: CaseFeedback, existing: list[Preference] | None = None) -> list[Preference]:
    """Fold a CaseFeedback into the preference set: add a new rule, or reinforce an existing one.

    Identity is (profile, action, pattern). A repeat bumps ``weight`` and appends the source
    topic (deduped); a novel mark appends a new Preference. Returns a new list; inputs are not
    mutated."""
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
        p = Preference(
            profile=feedback.profile, action=action, pattern=pattern,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_distill.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/preferences.py tests/rehearsal/test_preferences_distill.py
git commit -m "feat(rehearsal): distil surgeon marks into reinforced operative preferences"
```

---

### Task 3: Apply preferences to a manifest

**Files:**
- Modify: `neuro_caseboard/preferences.py` (append `_card_signature`, `_matches`, `apply_preferences`)
- Test: `tests/rehearsal/test_preferences_apply.py`

**Interfaces:**
- Consumes: `Preference` (Task 2); `QuestionCard`, `QuestionManifest` (caseprep).
- Produces: `apply_preferences(manifest, profile, prefs)->QuestionManifest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_preferences_apply.py
"""Re-express a stored preference set against a fresh manifest (suppress / add / elevate)."""
from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest
from neuro_caseboard.preferences import Preference, apply_preferences, _key_terms


def _card(q, tf="04-operative-plan.md"):
    return QuestionCard(target_file=tf, section_key="critical_steps", question=q,
                        why_it_matters="w", compiler_slot="Critical Steps")


def _manifest(*questions):
    return QuestionManifest(procedure_family="generic", cards=[_card(q) for q in questions])


def test_none_or_empty_is_noop():
    m = _manifest("alpha step", "beta step")
    assert apply_preferences(m, "spine", None) is m
    assert apply_preferences(m, "spine", []) is m


def test_suppress_drops_matching_card():
    m = _manifest("positioning prone checklist", "vertebral artery control")
    pref = Preference(profile="spine", action="suppress",
                      pattern=_key_terms("positioning prone checklist"))
    out = apply_preferences(m, "spine", [pref])
    qs = [c.question for c in out.cards]
    assert "positioning prone checklist" not in qs
    assert "vertebral artery control" in qs


def test_add_injects_when_absent_but_not_when_present():
    m = _manifest("vertebral artery control")
    add = Preference(profile="spine", action="add",
                     pattern=_key_terms("fusion construct plan"),
                     text="Confirm fusion construct plan", why="always")
    out = apply_preferences(m, "spine", [add])
    assert any("fusion construct plan" in c.question for c in out.cards)
    # idempotent: applying again does not duplicate
    out2 = apply_preferences(out, "spine", [add])
    assert sum("fusion construct plan" in c.question for c in out2.cards) == 1


def test_elevate_moves_matching_card_to_front():
    m = _manifest("alpha step", "beta gamma elevate-me", "delta step")
    pref = Preference(profile="spine", action="elevate",
                      pattern=_key_terms("beta gamma elevate-me"))
    out = apply_preferences(m, "spine", [pref])
    assert out.cards[0].question == "beta gamma elevate-me"


def test_profile_scoping_skips_other_profiles():
    m = _manifest("positioning prone checklist")
    pref = Preference(profile="skull_base", action="suppress",
                      pattern=_key_terms("positioning prone checklist"))
    out = apply_preferences(m, "spine", [pref])           # spine build, skull_base pref
    assert [c.question for c in out.cards] == ["positioning prone checklist"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_apply.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_preferences'`

- [ ] **Step 3: Write minimal implementation** (append to `neuro_caseboard/preferences.py`)

```python
from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest


def _card_signature(card: QuestionCard) -> str:
    return _key_terms(f"{card.question} {card.why_it_matters}")


def _matches(pattern: str, card: QuestionCard) -> bool:
    """A card matches a preference when every term in the pattern appears in the card's
    signature (subset match) — robust to extra words and ordering."""
    pat = set(pattern.split())
    return bool(pat) and pat <= set(_card_signature(card).split())


def apply_preferences(manifest: QuestionManifest, profile: str,
                      prefs: list[Preference] | None) -> QuestionManifest:
    """Re-express stored preferences against a fresh manifest. Profile-scoped (a pref applies
    when its profile is "" or == the build profile). Order is suppress -> add -> elevate, so an
    added card can itself be elevated and a suppressed card never lingers. Returns a NEW
    manifest (frozen inputs are never mutated); returns the input unchanged when there is
    nothing to apply."""
    if not prefs:
        return manifest
    active = [p for p in prefs if p.profile in ("", profile)]
    if not active:
        return manifest
    cards = list(manifest.cards)

    sup = [p.pattern for p in active if p.action == "suppress"]
    if sup:
        cards = [c for c in cards if not any(_matches(pat, c) for pat in sup)]

    for p in [p for p in active if p.action == "add"]:
        if any(_matches(p.pattern, c) for c in cards):
            continue
        cards.append(QuestionCard(
            target_file=p.target_file, section_key=p.section_key,
            question=p.text, why_it_matters=p.why or _default_why("add"),
            compiler_slot=p.compiler_slot))

    elev = [p.pattern for p in active if p.action == "elevate"]
    if elev:
        def _is_elevated(c: QuestionCard) -> bool:
            return any(_matches(pat, c) for pat in elev)
        # Stable global partition. The compiler pins section order (its `order` list) and
        # renders cards within a section in list order, so front-of-list within a target_file
        # group renders first in that section.
        cards = [c for c in cards if _is_elevated(c)] + [c for c in cards if not _is_elevated(c)]

    return QuestionManifest(
        procedure_family=getattr(manifest, "procedure_family", "generic"), cards=cards)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_apply.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/preferences.py tests/rehearsal/test_preferences_apply.py
git commit -m "feat(rehearsal): apply remembered preferences to a question manifest"
```

---

### Task 4: Thread `prefs` through the pipeline

**Files:**
- Modify: `neuro_caseboard/pipeline.py` (`build_manifest`, `build_dossier`, `build_case_dossier`, `generate`, `generate_case`)
- Test: `tests/rehearsal/test_pipeline_prefs.py`

**Interfaces:**
- Consumes: `apply_preferences`, `Preference`, `_key_terms` (Tasks 2–3).
- Produces: optional `prefs=None` keyword on `build_manifest`, `build_dossier`, `build_case_dossier`, `generate`, `generate_case`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_pipeline_prefs.py
"""prefs threaded through the offline build path: default no-op; suppress drops; add injects."""
from neuro_caseboard.pipeline import build_manifest, build_dossier
from neuro_caseboard.preferences import Preference, _key_terms


def test_prefs_default_is_noop():
    a, _ = build_manifest("C5-6 corpectomy", use_llm=False)
    b, _ = build_manifest("C5-6 corpectomy", use_llm=False, prefs=None)
    assert [c.question for c in a.cards] == [c.question for c in b.cards]


def test_build_dossier_suppress_removes_a_claim():
    topic = "C5-6 corpectomy"
    base, profile = build_manifest(topic, use_llm=False)
    target = base.cards[0]
    pref = Preference(profile=profile, action="suppress",
                      pattern=_key_terms(f"{target.question} {target.why_it_matters}"))
    d0 = build_dossier(topic, enrich=False, use_llm=False)
    d1 = build_dossier(topic, enrich=False, use_llm=False, prefs=[pref])
    n0 = sum(len(s.claims) for s in d0.sections)
    n1 = sum(len(s.claims) for s in d1.sections)
    assert n1 < n0


def test_build_dossier_add_injects_a_claim():
    pref = Preference(profile="spine", action="add",
                      pattern=_key_terms("intraoperative monitoring troubleshooting xenon"),
                      text="Confirm intraoperative monitoring troubleshooting plan xenon",
                      why="Surgeon always wants this.",
                      target_file="04-operative-plan.md", section_key="critical_steps",
                      compiler_slot="Critical Steps")
    d = build_dossier("C5-6 corpectomy", enrich=False, use_llm=False, prefs=[pref])
    blob = " ".join(" ".join([c.text, c.why, *c.sub_items])
                    for s in d.sections for c in s.claims)
    assert "xenon" in blob
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_pipeline_prefs.py -q`
Expected: FAIL — `TypeError: build_manifest() got an unexpected keyword argument 'prefs'`

- [ ] **Step 3: Write minimal implementation** (four edits in `neuro_caseboard/pipeline.py`)

3a. `build_manifest` — add `prefs=None` and apply after prune. Replace the signature line and the final `return`:

```python
def build_manifest(topic: str, *, use_llm=None, prefs=None):
```

Replace the trailing `return prune_offtarget(manifest, topic), profile` with:

```python
    pruned = prune_offtarget(manifest, topic)
    if prefs:
        from neuro_caseboard.preferences import apply_preferences
        pruned = apply_preferences(pruned, profile, prefs)
    return pruned, profile
```

3b. `build_dossier` — add `prefs=None` and pass it to `build_manifest`:

```python
def build_dossier(topic: str, *, enrich: bool = True, use_llm=None, prefs=None):
    """Run the full pipeline and return a compiled Dossier."""
    manifest, _profile = build_manifest(topic, use_llm=use_llm, prefs=prefs)
```

3c. `build_case_dossier` — add `prefs=None` to the signature and apply right after the existing `manifest = prune_offtarget(manifest, topic)` line:

```python
def build_case_dossier(case, *, enrich: bool = True, use_llm=None, literature=None,
                       lit_client=None, lit_synth_client=None, lit_cache=None,
                       figures_dir=None, fig_complete_fn=None, retriever=None,
                       fig_retriever=None, prefs=None):
```

Immediately after `manifest = prune_offtarget(manifest, topic)        # anti-bleed (LOOP_PROMPT §6)` add:

```python
    if prefs:
        from neuro_caseboard.preferences import apply_preferences
        manifest = apply_preferences(manifest, classify_profile(topic), prefs)
```

3d. `generate` and `generate_case` — thread `prefs` through. Replace the `generate` signature/body call:

```python
def generate(topic: str, *, output_dir, pdf: bool = False, enrich: bool = True, use_llm=None,
             prefs=None):
    """Build a dossier and write case-board.md (+ case-board.pdf) to output_dir."""
    dossier = build_dossier(topic, enrich=enrich, use_llm=use_llm, prefs=prefs)
```

And `generate_case` — add `prefs=None` to the signature and pass it to `build_case_dossier`:

```python
def generate_case(dictation: str, *, output_dir, pdf: bool = False, enrich: bool = True,
                  use_llm=None, literature=None, prefs=None):
```

Change its `dossier = build_case_dossier(...)` call to include `prefs=prefs`:

```python
    dossier = build_case_dossier(case, enrich=enrich, use_llm=use_llm, literature=literature,
                                 figures_dir=out, prefs=prefs)
```

- [ ] **Step 4: Run the new test AND the existing pipeline test (no regressions)**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_pipeline_prefs.py tests/test_pipeline.py -q`
Expected: PASS (all green — new prefs behavior works; existing pipeline tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/pipeline.py tests/rehearsal/test_pipeline_prefs.py
git commit -m "feat(rehearsal): apply operative preferences in build_manifest/build_dossier/build_case_dossier"
```

---

### Task 5: CLI — `feedback` subcommand + `--prefs` flag

**Files:**
- Modify: `neuro_caseboard/cli.py`
- Test: `tests/rehearsal/test_cli_feedback.py`

**Interfaces:**
- Consumes: `load_feedback` (Task 1); `load_preferences`, `save_preferences`, `distill` (Task 2); `generate`/`generate_case` `prefs=` (Task 4).
- Produces: `caseboard feedback --marks <json> [--store <json>]`; `--prefs <json>` on `build` and `case`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_cli_feedback.py
"""CLI: record marks into the preferences store, and apply the store on build."""
import json

from neuro_caseboard.cli import main


def test_feedback_records_preferences(tmp_path, capsys):
    marks = {"topic": "C5-6 corpectomy", "profile": "spine", "items": [
        {"mark": "important", "text": "Vertebral artery course at C1-2",
         "target_file": "03-anatomy-at-risk.md"},
        {"mark": "missing", "text": "Confirm fusion construct plan",
         "target_file": "04-operative-plan.md"}]}
    mpath = tmp_path / "marks.json"
    mpath.write_text(json.dumps(marks))
    store = tmp_path / "prefs.json"

    rc = main(["feedback", "--marks", str(mpath), "--store", str(store)])
    assert rc == 0
    saved = json.loads(store.read_text())
    assert {p["action"] for p in saved} == {"elevate", "add"}
    assert all(p["profile"] == "spine" for p in saved)
    assert "Preferences" in capsys.readouterr().out


def test_build_accepts_prefs_flag_offline(tmp_path):
    store = tmp_path / "prefs.json"
    store.write_text(json.dumps([{
        "profile": "spine", "action": "add",
        "pattern": "monitoring troubleshooting xenon",
        "text": "Confirm intraoperative monitoring troubleshooting plan xenon",
        "why": "always", "target_file": "04-operative-plan.md",
        "section_key": "critical_steps", "compiler_slot": "Critical Steps",
        "weight": 1, "sources": ["C5-6 corpectomy"]}]))
    out = tmp_path / "board"
    rc = main(["build", "C5-6 corpectomy", "-o", str(out),
               "--no-enrich", "--no-llm", "--prefs", str(store)])
    assert rc == 0
    md = (out / "case-board.md").read_text()
    assert "xenon" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_cli_feedback.py -q`
Expected: FAIL — `SystemExit: 2` (argparse rejects the unknown `feedback` subcommand / `--prefs` flag)

- [ ] **Step 3: Write minimal implementation** (three edits in `neuro_caseboard/cli.py`)

3a. Add the `feedback` handler (place after `_run_case`):

```python
def _run_feedback(args) -> int:
    from neuro_caseboard.feedback import load_feedback
    from neuro_caseboard.preferences import distill, load_preferences, save_preferences
    fb = load_feedback(args.marks)
    existing = load_preferences(args.store)
    updated = distill(fb, existing)
    save_preferences(updated, args.store)
    new = len(updated) - len(existing)
    print(f"Recorded {len(fb.items)} mark(s) from '{fb.topic}'. "
          f"Preferences: {len(updated)} total ({new} new, {len(updated) - new} reinforced). "
          f"Stored at {args.store}.")
    return 0
```

3b. Thread `--prefs` through `_run_build` and `_run_case`. Replace the `generate(...)` call in `_run_build`:

```python
    prefs = None
    if getattr(args, "prefs", None):
        from neuro_caseboard.preferences import load_preferences
        prefs = load_preferences(args.prefs)
    dossier, artifacts = generate(
        args.topic, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich,
        use_llm=False if args.no_llm else None, prefs=prefs)
```

And the `generate_case(...)` call in `_run_case`:

```python
    prefs = None
    if getattr(args, "prefs", None):
        from neuro_caseboard.preferences import load_preferences
        prefs = load_preferences(args.prefs)
    case, dossier, artifacts = generate_case(
        args.dictation, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich,
        use_llm=False if args.no_llm else None,
        literature=False if args.no_literature else None, prefs=prefs)
```

3c. Register the parser + flags. Add `--prefs` to the `build` (`b`) and `case` (`cs`) parsers:

```python
    b.add_argument("--prefs", default=None,
                   help="Apply a stored operative-preferences JSON to this build")
```

```python
    cs.add_argument("--prefs", default=None,
                    help="Apply a stored operative-preferences JSON to this case build")
```

Add the `feedback` subparser (after the `cards` parser block):

```python
    fb = sub.add_parser(
        "feedback",
        help="Record surgeon marks on a board into the operative-preferences memory")
    fb.add_argument("--marks", required=True,
                    help="Path to a CaseFeedback JSON (wrong/missing/important marks)")
    fb.add_argument("--store", default="operative-preferences.json",
                    help="Preferences store JSON to create/update")
```

Add the dispatch line (with the other `if args.cmd == ...` checks):

```python
    if args.cmd == "feedback":
        return _run_feedback(args)
```

- [ ] **Step 4: Run the new test AND the CLI smoke test (no regressions)**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_cli_feedback.py tests/test_cli_smoke.py -q`
Expected: PASS (all green)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cli.py tests/rehearsal/test_cli_feedback.py
git commit -m "feat(rehearsal): caseboard feedback subcommand + --prefs on build/case"
```

---

### Task 6: End-to-end loop proof + runbook

**Files:**
- Create: `tests/rehearsal/test_loop_end_to_end.py`
- Create: `docs/runbooks/2026-06-19-surgeon-in-the-loop.md`

**Interfaces:**
- Consumes: everything from Tasks 1–5.

- [ ] **Step 1: Write the failing test** (the closed loop: board → mark → distil → rebuild → board changed)

```python
# tests/rehearsal/test_loop_end_to_end.py
"""The closed surgeon-in-the-loop: a board, marked, remembered, regenerates differently."""
from neuro_caseboard.feedback import CaseFeedback, FeedbackItem
from neuro_caseboard.preferences import distill
from neuro_caseboard.pipeline import build_dossier, build_manifest, classify_profile


def _blobs(d):
    # text + sub_items, so an added consideration is found whether it lands in the claim
    # text or (for a compound question) in the checkbox sub-items.
    return [" ".join([c.text, *c.sub_items]) for s in d.sections for c in s.claims]


def test_marks_remembered_change_the_next_board():
    topic = "C5-6 corpectomy"
    profile = classify_profile(topic)
    base = build_dossier(topic, enrich=False, use_llm=False)

    # Surgeon marks the board: one existing claim is wrong, plus a missing consideration.
    first_card = build_manifest(topic, use_llm=False)[0].cards[0]
    # compile.py stamps each Claim with raw == its source card's question — the reliable handle
    # for "did this card's claim survive?" (robust to scrubbing and suppress+add count parity).
    base_raws = [c.raw for s in base.sections for c in s.claims]
    assert first_card.question in base_raws          # sanity: the marked claim WAS on the board

    fb = CaseFeedback(topic=topic, profile=profile, items=[
        FeedbackItem(mark="wrong", text=f"{first_card.question} {first_card.why_it_matters}"),
        FeedbackItem(mark="missing",
                     text="Confirm intraoperative monitoring troubleshooting plan zenith",
                     target_file="04-operative-plan.md"),
    ])
    prefs = distill(fb)                              # the remembered operative heuristics

    after = build_dossier(topic, enrich=False, use_llm=False, prefs=prefs)
    after_raws = [c.raw for s in after.sections for c in s.claims]

    # "missing" consideration is now on the board, and was not before ...
    assert any("zenith" in b for b in _blobs(after))
    assert not any("zenith" in b for b in _blobs(base))
    # ... and the "wrong" claim is gone (its source card no longer renders).
    assert first_card.question not in after_raws

    # The memory is reusable across a *different* case of the same profile.
    other = build_dossier("C3-4 ACDF", enrich=False, use_llm=False, prefs=prefs)
    assert any("zenith" in b for b in _blobs(other))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_loop_end_to_end.py -q`
Expected: FAIL (the file is new; confirm RED before writing the runbook, then GREEN once Tasks 1–5 are in — if Tasks 1–5 are already merged this should pass immediately, which is the intended proof).

- [ ] **Step 3: Write the runbook**

```markdown
# Runbook — Surgeon-in-the-Loop Operative Rehearsal (feedback + remembered preferences)

The loop closes the gap between "generate a dossier" and a board that learns the surgeon's
operative preferences.

## The loop
1. **Generate a board.** `caseboard build "C5-6 corpectomy"` (or `caseboard case "<dictation>"`).
2. **Mark it.** Author a `CaseFeedback` JSON — `wrong` (drop this), `missing` (add this),
   `important` (elevate this) — e.g. `marks.json`:
   ```json
   {"topic": "C5-6 corpectomy", "profile": "spine", "items": [
     {"mark": "important", "text": "Vertebral artery course at C1-2", "target_file": "03-anatomy-at-risk.md"},
     {"mark": "missing", "text": "Confirm fusion construct plan", "target_file": "04-operative-plan.md"}]}
   ```
   (`profile` is `spine` | `skull_base` | `vascular` | "" — it scopes which future boards the
   preference applies to. Get it from `classify_profile(topic)`.)
3. **Remember.** `caseboard feedback --marks marks.json --store operative-preferences.json`
   distils the marks into reusable preferences (reinforced across cases by `weight`).
4. **Regenerate.** `caseboard build "C5-6 corpectomy" --prefs operative-preferences.json` — the
   board now drops `wrong` content, surfaces `missing` considerations, and elevates `important`
   ones. The same store applies to *any* later case of that profile.

## Design notes
- The feedback axis (`wrong`/`missing`/`important`) is distinct from the evidence axis
  (`supported`/`verify`) in `model.py`.
- Preferences are case-INDEPENDENT (keyed by `profile`), so they generalize — a heuristic learned
  on one C5-6 case applies to the next cervical case.
- Application happens after the anti-bleed `prune_offtarget` guard, on the same `QuestionCard`
  manifest both `build` and `case` already use, so the memory rides existing machinery.
- The interactive paste/edit/mark UI is the separate web-frontend workstream; this is the engine.
```

- [ ] **Step 4: Run the full scoped harness (whole feature green, no regressions)**

Run: `.loopvenv/bin/python -m pytest -p no:cacheprovider -q tests/test_pipeline.py tests/test_compile.py tests/test_render_md.py tests/test_board_view.py tests/test_topic_extract.py tests/rehearsal`
Expected: PASS (baseline 92 + all new rehearsal tests)

- [ ] **Step 5: Commit**

```bash
git add tests/rehearsal/test_loop_end_to_end.py docs/runbooks/2026-06-19-surgeon-in-the-loop.md
git commit -m "test(rehearsal): end-to-end surgeon-in-the-loop proof + runbook"
```

---

## Self-Review

**1. Spec coverage.**
- "surgeon marks wrong/missing/important" → Task 1 (`FeedbackItem.mark` ∈ `MARKS`). ✓
- "system updates the case board" → Tasks 3–4 (`apply_preferences` suppress/add/elevate in `build_dossier`/`build_case_dossier`). ✓
- "remembers reusable operative heuristics/preferences" → Task 2 (`distill` → persisted `Preference`, reinforced by `weight`, keyed by `profile` = case-independent). ✓
- "paste → extract structured case → edit → generate board" → **already shipped** (`intake.py`/`CaseContext`/`build_case_dossier`); this plan layers feedback+memory on top without regressing it (Task 4 default no-op; `case` path also accepts `prefs`). ✓
- Closed loop demonstrated end-to-end → Task 6. ✓

**2. Placeholder scan.** No "TBD"/"handle edge cases"/"similar to Task N" — every code step is complete and runnable. ✓

**3. Type consistency.** `apply_preferences(manifest, profile, prefs)` used identically in Tasks 3–4. `Preference` field names (`profile, action, pattern, text, why, target_file, section_key, compiler_slot, weight, sources`) are identical across distill (Task 2), apply (Task 3), the CLI store JSON (Task 5), and tests. `distill(feedback, existing=None)`, `load_preferences(path)`, `save_preferences(prefs, path)`, `load_feedback(path)` signatures match every call site. `_key_terms` reused everywhere a signature is computed. ✓

**Notes for the implementer.**
- `QuestionCard`/`QuestionManifest` are **frozen** — always build new instances (the code does).
- Apply preferences strictly **after** `prune_offtarget`, so an injected card is never stripped.
- Keep `prefs=None` a no-op so the existing 92-test baseline stays green (Task 4 Step 4 verifies this).
