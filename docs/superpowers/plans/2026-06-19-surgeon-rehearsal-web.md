# Surgeon-in-the-Loop Rehearsal (web-first): mark the board → remember operative preferences → board updates

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the react-bits web console, let a surgeon mark a generated board wrong / missing / important; the system distils those marks into reusable, profile-keyed operative preferences and regenerates the board (and every later board of that subspecialty) to reflect them.

**Architecture:** Engine primitives (`feedback.py`, `preferences.py`) + one optional `prefs` parameter threaded through the pipeline (no-op by default) → a thin FastAPI surface (`POST /api/feedback`, `GET /api/preferences`, `use_prefs` on `/api/build`) over the SAME `build_dossier` the CLI/Streamlit use → a "Rehearsal mode" on the web Build page that marks claims and renders the updated board. The engine stays authoritative; nothing fabricates a board.

**Tech Stack:** Python 3.10+ (stdlib `dataclasses`/`json`/`re`), vendored `caseprep.explorer.question_manifest`, FastAPI (in `.loopvenv`), pytest + `fastapi.testclient`; web = Vite + React 19 + TS + Tailwind v4 (existing `web/`), verified with `npm run build` + Playwright.

## Global Constraints

- **Engine modules are stdlib-only + fully offline.** Tests inject fakes / use offline flags (`enrich=False, use_llm=False`). Never call a live LLM/GPU/network.
- **Default path unchanged:** `prefs=None`/absent and `use_prefs=False` are no-ops. The existing scoped harness (92 tests) MUST stay green.
- **Clinically conservative guardrails:** `add`/`elevate` apply immediately; a single `wrong` mark (weight 1) only **de-emphasizes** (moves the claim to the END of its section); **removal requires weight ≥ 2** (marked wrong on ≥2 cases). Never delete safety content on one mark.
- **Memory keyed by `profile`** (`classify_profile`: spine/skull_base/vascular/""=any).
- **Feedback axis is DISTINCT** from the evidence `status` axis in `model.py`.
- `QuestionCard`/`QuestionManifest` are **frozen** → build new objects. Apply prefs **after** `prune_offtarget`.
- caseprep is **vendored** — `from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest`. Install only `pip install -e .[dev]`.
- **No auth** on the API (local single-user; matches the web-frontend-loop spec). Honest degradation — forward the engine's real result or its real error.
- New engine/API tests under `tests/rehearsal/`. Automated harness (every VERIFY):
  `.loopvenv/bin/python -m pytest -p no:cacheprovider -q tests/test_pipeline.py tests/test_compile.py tests/test_render_md.py tests/test_board_view.py tests/test_topic_extract.py tests/rehearsal`
  Web is verified per web-task with `cd web && npm install` (once) + `npm run build`, plus a headless Playwright screenshot of `/build` rehearsal mode (the web-loop's "RUN and observe" gate; repo CI is Python-only).

---

## File Structure

- `neuro_caseboard/feedback.py` (**create**) — `MARKS`, `FeedbackItem`, `CaseFeedback`, `target_file_for_heading`, save/load JSON.
- `neuro_caseboard/preferences.py` (**create**) — `ACTIONS`, `Preference`, `_key_terms`, `distill`, `_matches`, `apply_preferences`, `default_store_path`, save/load JSON.
- `neuro_caseboard/pipeline.py` (**modify**) — optional `prefs=None` on `build_manifest`/`build_dossier`/`build_case_dossier`.
- `api/server.py` (**modify**) — `POST /api/feedback`, `GET /api/preferences`, `use_prefs` on `/api/build`.
- `web/src/lib/api.ts` (**modify**) — feedback/preferences clients + types; `use_prefs` on build.
- `web/src/components/build/DossierView.tsx` (**modify**) — optional rehearsal props (per-claim mark controls, per-section "+ missing").
- `web/src/components/build/RememberedPanel.tsx` (**create**) — shows what was remembered.
- `web/src/pages/Build.tsx` (**modify**) — Rehearsal-mode toggle, marks state, submit → `/api/feedback`.
- `tests/rehearsal/test_feedback.py`, `test_preferences_distill.py`, `test_preferences_apply.py`, `test_pipeline_prefs.py`, `test_api_feedback.py` (**create**).
- `docs/runbooks/2026-06-19-surgeon-in-the-loop.md` (**create**).

---

### Task 1: Feedback model + JSON persistence — ✅ DONE (VERIFY #5: 96 pass / 0 fail; commit 57c012b)

**Files:** Create `neuro_caseboard/feedback.py`; Test `tests/rehearsal/test_feedback.py`.

**Interfaces — Produces:** `MARKS`; `FeedbackItem(mark, text, target_file="04-operative-plan.md", section_key="critical_steps", compiler_slot="Critical Steps", note="")`; `CaseFeedback(topic, profile="", items=[])` with `to_dict`/`from_dict`; `target_file_for_heading(heading)->str`; `save_feedback`/`load_feedback`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_feedback.py
"""Feedback model + JSON round-trip + heading→target_file resolver."""
import pytest
from neuro_caseboard.feedback import (
    MARKS, FeedbackItem, CaseFeedback, save_feedback, load_feedback, target_file_for_heading,
)


def test_marks_axis():
    assert set(MARKS) == {"wrong", "missing", "important"}


def test_item_rejects_unknown_mark():
    with pytest.raises(ValueError):
        FeedbackItem(mark="bogus", text="x")


def test_heading_resolves_to_target_file():
    assert target_file_for_heading("Anatomy at Risk") == "03-anatomy-at-risk.md"
    assert target_file_for_heading("Operative Plan") == "04-operative-plan.md"
    assert target_file_for_heading("Risk and Rescue") == "05-risk-and-rescue.md"
    assert target_file_for_heading("") == "04-operative-plan.md"  # sensible default


def test_round_trip(tmp_path):
    fb = CaseFeedback(topic="C5-6 corpectomy", profile="spine", items=[
        FeedbackItem(mark="important", text="Vertebral artery course", target_file="03-anatomy-at-risk.md"),
        FeedbackItem(mark="missing", text="Confirm fusion construct plan", note="I always fuse"),
    ])
    p = save_feedback(fb, tmp_path / "marks.json")
    assert load_feedback(p) == fb
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_feedback.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.feedback'`

- [ ] **Step 3: Write minimal implementation**

```python
# neuro_caseboard/feedback.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_feedback.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/feedback.py tests/rehearsal/test_feedback.py
git commit -m "feat(rehearsal): surgeon board-feedback model + JSON persistence"
```

---

### Task 2: Preference model + distillation

**Files:** Create `neuro_caseboard/preferences.py`; Test `tests/rehearsal/test_preferences_distill.py`.

**Interfaces — Consumes:** `CaseFeedback`/`FeedbackItem`. **Produces:** `ACTIONS`; `_key_terms(text)->str`; `Preference(profile, action, pattern, text="", why="", target_file="04-operative-plan.md", section_key="critical_steps", compiler_slot="Critical Steps", weight=1, sources=[])`; `distill(feedback, existing=None)->list[Preference]`; `default_store_path()->Path`; `save_preferences`/`load_preferences`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_preferences_distill.py
"""Distil marks into reusable, reinforced, profile-keyed preferences."""
from neuro_caseboard.feedback import CaseFeedback, FeedbackItem
from neuro_caseboard.preferences import (
    distill, save_preferences, load_preferences, _key_terms,
)


def _fb(topic, *items):
    return CaseFeedback(topic=topic, profile="spine", items=list(items))


def test_marks_map_to_actions():
    prefs = distill(_fb("C5-6 corpectomy",
                        FeedbackItem(mark="wrong", text="Generic positioning checklist"),
                        FeedbackItem(mark="important", text="Vertebral artery course"),
                        FeedbackItem(mark="missing", text="Confirm fusion construct plan")))
    assert {p.action for p in prefs} == {"suppress", "elevate", "add"}
    assert all(p.profile == "spine" for p in prefs)
    assert all(p.weight == 1 for p in prefs)


def test_reinforce_repeat_across_cases():
    p1 = distill(_fb("C5-6 corpectomy", FeedbackItem(mark="wrong", text="Generic positioning checklist")))
    p2 = distill(_fb("C1-2 fusion", FeedbackItem(mark="wrong", text="checklist for generic positioning")),
                 p1)  # same key terms
    assert len(p2) == 1 and p2[0].weight == 2
    assert set(p2[0].sources) == {"C5-6 corpectomy", "C1-2 fusion"}


def test_key_terms_order_independent():
    assert _key_terms("Vertebral artery course") == _key_terms("course of the artery, vertebral")


def test_round_trip(tmp_path):
    prefs = distill(_fb("t", FeedbackItem(mark="wrong", text="Generic positioning checklist")))
    p = save_preferences(prefs, tmp_path / "p.json")
    assert load_preferences(p) == prefs
    assert load_preferences(tmp_path / "absent.json") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_distill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.preferences'`

- [ ] **Step 3: Write minimal implementation**

```python
# neuro_caseboard/preferences.py
"""Remembered operative preferences — the memory half of the surgeon-in-the-loop.

Surgeon marks distil into reusable, case-INDEPENDENT ``Preference`` rules keyed by ``profile``.
Re-encountering the same (profile, action, pattern) bumps ``weight`` and records the source case
(provenance), so a repeatedly-asserted heuristic is reinforced — which the conservative guardrail
in ``apply_preferences`` (Task 3) uses to gate removal. Pure, stdlib-only, offline.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_distill.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/preferences.py tests/rehearsal/test_preferences_distill.py
git commit -m "feat(rehearsal): distil marks into reinforced, profile-keyed preferences"
```

---

### Task 3: Apply preferences (conservative guardrails)

**Files:** Modify `neuro_caseboard/preferences.py` (append); Test `tests/rehearsal/test_preferences_apply.py`.

**Interfaces — Produces:** `apply_preferences(manifest, profile, prefs)->QuestionManifest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_preferences_apply.py
"""Apply preferences to a manifest: conservative suppress, plus add/elevate/profile-scope."""
from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest
from neuro_caseboard.preferences import Preference, apply_preferences, _key_terms


def _card(q):
    return QuestionCard(target_file="04-operative-plan.md", section_key="critical_steps",
                        question=q, why_it_matters="w", compiler_slot="Critical Steps")


def _m(*qs):
    return QuestionManifest(procedure_family="generic", cards=[_card(q) for q in qs])


def test_noop():
    m = _m("a step", "b step")
    assert apply_preferences(m, "spine", None) is m
    assert apply_preferences(m, "spine", []) is m


def test_single_wrong_deemphasizes_not_removes():
    m = _m("alpha step", "beta deprio target", "gamma step")
    pref = Preference(profile="spine", action="suppress",
                      pattern=_key_terms("beta deprio target"), weight=1)
    out = apply_preferences(m, "spine", [pref])
    qs = [c.question for c in out.cards]
    assert "beta deprio target" in qs        # retained — single mark never deletes
    assert qs[-1] == "beta deprio target"    # moved to end (de-emphasized)


def test_reinforced_wrong_removes():
    m = _m("alpha step", "beta deprio target", "gamma step")
    pref = Preference(profile="spine", action="suppress",
                      pattern=_key_terms("beta deprio target"), weight=2)
    out = apply_preferences(m, "spine", [pref])
    assert "beta deprio target" not in [c.question for c in out.cards]


def test_add_injects_once():
    m = _m("vertebral artery control")
    add = Preference(profile="spine", action="add", pattern=_key_terms("fusion construct plan"),
                     text="Confirm fusion construct plan", why="always")
    out = apply_preferences(m, "spine", [add])
    assert any("fusion construct plan" in c.question for c in out.cards)
    out2 = apply_preferences(out, "spine", [add])
    assert sum("fusion construct plan" in c.question for c in out2.cards) == 1


def test_elevate_moves_to_front():
    m = _m("alpha step", "beta gamma liftme", "delta step")
    pref = Preference(profile="spine", action="elevate", pattern=_key_terms("beta gamma liftme"))
    assert apply_preferences(m, "spine", [pref]).cards[0].question == "beta gamma liftme"


def test_profile_scope():
    m = _m("positioning prone checklist")
    pref = Preference(profile="skull_base", action="suppress",
                      pattern=_key_terms("positioning prone checklist"), weight=2)
    assert [c.question for c in apply_preferences(m, "spine", [pref]).cards] == ["positioning prone checklist"]
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
    pat = set(pattern.split())
    return bool(pat) and pat <= set(_card_signature(card).split())


def apply_preferences(manifest: QuestionManifest, profile: str,
                      prefs: list[Preference] | None) -> QuestionManifest:
    """Re-express stored preferences against a fresh manifest. Profile-scoped. Conservative:
    a ``suppress`` pref with weight>=2 REMOVES matching cards; weight<2 only DE-EMPHASIZES them
    (stable-move to the END of their target_file group — content retained). ``add`` injects when
    absent; ``elevate`` moves matching cards to the front. Order: suppress -> add -> elevate. New
    frozen manifest; input unchanged."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_preferences_apply.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/preferences.py tests/rehearsal/test_preferences_apply.py
git commit -m "feat(rehearsal): conservative apply_preferences (de-emphasize<2, remove>=2, add, elevate)"
```

---

### Task 4: Thread `prefs` through the pipeline

**Files:** Modify `neuro_caseboard/pipeline.py`; Test `tests/rehearsal/test_pipeline_prefs.py`.

**Interfaces — Produces:** optional `prefs=None` on `build_manifest`, `build_dossier`, `build_case_dossier`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_pipeline_prefs.py
"""prefs threaded through the offline build: default no-op; add injects; reinforced suppress removes."""
from neuro_caseboard.pipeline import build_manifest, build_dossier
from neuro_caseboard.preferences import Preference, _key_terms


def test_default_noop():
    a, _ = build_manifest("C5-6 corpectomy", use_llm=False)
    b, _ = build_manifest("C5-6 corpectomy", use_llm=False, prefs=None)
    assert [c.question for c in a.cards] == [c.question for c in b.cards]


def test_add_injects_into_board():
    pref = Preference(profile="spine", action="add",
                      pattern=_key_terms("monitoring troubleshooting zenith"),
                      text="Confirm intraoperative monitoring troubleshooting plan zenith", why="always")
    d = build_dossier("C5-6 corpectomy", enrich=False, use_llm=False, prefs=[pref])
    blob = " ".join(" ".join([c.text, *c.sub_items]) for s in d.sections for c in s.claims)
    assert "zenith" in blob


def test_reinforced_suppress_removes_claim():
    topic = "C5-6 corpectomy"
    base, profile = build_manifest(topic, use_llm=False)
    target = base.cards[0]
    pref = Preference(profile=profile, action="suppress",
                      pattern=_key_terms(f"{target.question} {target.why_it_matters}"), weight=2)
    d0 = build_dossier(topic, enrich=False, use_llm=False)
    d1 = build_dossier(topic, enrich=False, use_llm=False, prefs=[pref])
    raws0 = [c.raw for s in d0.sections for c in s.claims]
    raws1 = [c.raw for s in d1.sections for c in s.claims]
    assert target.question in raws0 and target.question not in raws1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_pipeline_prefs.py -q`
Expected: FAIL — `TypeError: build_manifest() got an unexpected keyword argument 'prefs'`

- [ ] **Step 3: Write minimal implementation** (three edits in `neuro_caseboard/pipeline.py`)

3a. `build_manifest` — add `prefs=None`; replace the final `return prune_offtarget(manifest, topic), profile` with:

```python
def build_manifest(topic: str, *, use_llm=None, prefs=None):
```
```python
    pruned = prune_offtarget(manifest, topic)
    if prefs:
        from neuro_caseboard.preferences import apply_preferences
        pruned = apply_preferences(pruned, profile, prefs)
    return pruned, profile
```

3b. `build_dossier` — add `prefs=None`, pass it through:

```python
def build_dossier(topic: str, *, enrich: bool = True, use_llm=None, prefs=None):
    """Run the full pipeline and return a compiled Dossier."""
    manifest, _profile = build_manifest(topic, use_llm=use_llm, prefs=prefs)
```

3c. `build_case_dossier` — add `prefs=None` to the signature; immediately after its existing
`manifest = prune_offtarget(manifest, topic)        # anti-bleed (LOOP_PROMPT §6)` line add:

```python
    if prefs:
        from neuro_caseboard.preferences import apply_preferences
        manifest = apply_preferences(manifest, classify_profile(topic), prefs)
```

- [ ] **Step 4: Run new + existing pipeline tests**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_pipeline_prefs.py tests/test_pipeline.py -q`
Expected: PASS (all green; existing pipeline behavior unchanged)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/pipeline.py tests/rehearsal/test_pipeline_prefs.py
git commit -m "feat(rehearsal): apply prefs in build_manifest/build_dossier/build_case_dossier"
```

---

### Task 5: API — `/api/feedback`, `/api/preferences`, `use_prefs` on `/api/build`

**Files:** Modify `api/server.py`; Test `tests/rehearsal/test_api_feedback.py`.

**Interfaces — Consumes:** Tasks 1–4. **Produces:** `POST /api/feedback`, `GET /api/preferences`, `BuildRequest.use_prefs`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rehearsal/test_api_feedback.py
"""API closed loop via FastAPI TestClient (offline build flags)."""
import json
from fastapi.testclient import TestClient
from api.server import app


def test_feedback_remembers_and_updates_board(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEBOARD_PREFS_STORE", str(tmp_path / "prefs.json"))
    client = TestClient(app)

    r = client.post("/api/feedback", json={
        "topic": "C5-6 corpectomy", "enrich": False, "use_llm": False,
        "items": [{"mark": "missing",
                   "text": "Confirm intraoperative monitoring troubleshooting plan zenith",
                   "section": "Operative Plan"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "dossier" and body["remembered"] >= 1
    assert "zenith" in json.dumps(body["dossier"])           # board updated immediately

    pr = client.get("/api/preferences").json()
    assert pr["count"] >= 1 and pr["preferences"][0]["profile"] == "spine"

    # the memory generalizes to a fresh build of the same profile
    b = client.post("/api/build", json={
        "topic": "C3-4 ACDF", "enrich": False, "use_llm": False, "use_prefs": True}).json()
    assert "zenith" in json.dumps(b["dossier"])

    # use_prefs=False ignores the store (unchanged default behavior)
    b2 = client.post("/api/build", json={
        "topic": "C3-4 ACDF", "enrich": False, "use_llm": False, "use_prefs": False}).json()
    assert "zenith" not in json.dumps(b2["dossier"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_api_feedback.py -q`
Expected: FAIL — 404 on `/api/feedback` (route not defined) → assertion error on `r.status_code`.

- [ ] **Step 3: Write minimal implementation** (edits in `api/server.py`)

3a. Add `use_prefs` to `BuildRequest` and a prefs-aware `_do_build`:

```python
class BuildRequest(BaseModel):
    topic: str
    enrich: bool = True
    use_llm: bool = True
    use_prefs: bool = True
```
```python
def _do_build(topic: str, enrich: bool, use_llm: bool, prefs=None):
    from neuro_caseboard.pipeline import build_dossier
    return build_dossier(topic, enrich=enrich, use_llm=None if use_llm else False, prefs=prefs)
```

3b. In `build()`, load + apply prefs when requested (replace the `dossier = _do_build(topic, req.enrich, req.use_llm)` line):

```python
    prefs = None
    if req.use_prefs:
        from neuro_caseboard.preferences import load_preferences, default_store_path
        prefs = load_preferences(default_store_path()) or None
    try:
        dossier = _do_build(topic, req.enrich, req.use_llm, prefs)
```

3c. Add the feedback + preferences endpoints (after `build_pdf`):

```python
class FeedbackMarkIn(BaseModel):
    mark: str
    text: str
    section: str = ""
    note: str = ""


class FeedbackRequest(BaseModel):
    topic: str
    profile: str = ""
    enrich: bool = False
    use_llm: bool = False
    items: list[FeedbackMarkIn]


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    topic = (req.topic or "").strip()
    if not topic:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty topic"})
    if not req.items:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "no marks"})

    from neuro_caseboard.pipeline import classify_profile
    from neuro_caseboard.feedback import CaseFeedback, FeedbackItem, target_file_for_heading
    from neuro_caseboard.preferences import (
        distill, load_preferences, save_preferences, default_store_path,
    )
    profile = req.profile or classify_profile(topic)
    items = [FeedbackItem(mark=m.mark, text=m.text,
                          target_file=target_file_for_heading(m.section), note=m.note)
             for m in req.items]
    fb = CaseFeedback(topic=topic, profile=profile, items=items)
    store = default_store_path()
    prefs = distill(fb, load_preferences(store))
    save_preferences(prefs, store)

    from neuro_core.gpu_guard import GpuNotReadyError
    try:
        dossier = _do_build(topic, req.enrich, req.use_llm, prefs)
    except GpuNotReadyError as e:
        return JSONResponse(status_code=503, content={"kind": "unavailable", "reason": f"GPU not ready: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"kind": "error", "error": f"{type(e).__name__}: {e}"})
    return {"kind": "dossier", "topic": topic, "profile": profile,
            "remembered": len(prefs), "dossier": _dossier_dict(dossier)}


@app.get("/api/preferences")
def preferences() -> dict:
    from dataclasses import asdict
    from neuro_caseboard.preferences import load_preferences, default_store_path
    prefs = load_preferences(default_store_path())
    return {"kind": "preferences", "count": len(prefs), "preferences": [asdict(p) for p in prefs]}
```

- [ ] **Step 4: Run new + a sanity engine test**

Run: `.loopvenv/bin/python -m pytest tests/rehearsal/test_api_feedback.py tests/rehearsal/test_pipeline_prefs.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/server.py tests/rehearsal/test_api_feedback.py
git commit -m "feat(rehearsal,api): /api/feedback + /api/preferences + use_prefs on /api/build"
```

---

### Task 6: Web — Rehearsal mode (mark the board, remember, re-render)

**Files:** Modify `web/src/lib/api.ts`, `web/src/components/build/DossierView.tsx`, `web/src/pages/Build.tsx`; Create `web/src/components/build/RememberedPanel.tsx`.

**Interfaces — Consumes:** `/api/feedback`, `/api/preferences`, `/api/build?use_prefs`. **Produces:** rehearsal UI.

> First run `cd web && npm install` once (node_modules is absent in a fresh worktree).

- [ ] **Step 1: Add the API client + types** (append to `web/src/lib/api.ts`)

```typescript
// ----- Rehearsal: feedback + remembered preferences -----------------------------------------

export type FeedbackMark = "wrong" | "missing" | "important"
export interface FeedbackItemIn { mark: FeedbackMark; text: string; section?: string; note?: string }

export type FeedbackResponse =
  | { kind: "dossier"; topic: string; profile: string; remembered: number; dossier: Dossier }
  | { kind: "unavailable"; reason: string }
  | { kind: "error"; error: string }

export async function submitFeedback(
  topic: string,
  items: FeedbackItemIn[],
  opts: { enrich: boolean; use_llm: boolean },
  signal?: AbortSignal,
): Promise<FeedbackResponse> {
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, items, enrich: opts.enrich, use_llm: opts.use_llm }),
    signal,
  })
  const data = (await res.json().catch(() => null)) as FeedbackResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

export interface PreferenceOut {
  profile: string; action: string; pattern: string; text: string; why: string
  weight: number; sources: string[]
}

export async function getPreferences(signal?: AbortSignal): Promise<{ count: number; preferences: PreferenceOut[] }> {
  const res = await fetch("/api/preferences", { signal })
  if (!res.ok) throw new Error(`/api/preferences returned ${res.status}`)
  return (await res.json()) as { count: number; preferences: PreferenceOut[] }
}
```

Also extend `buildDossier` to forward `use_prefs` (default true) — change its `opts` type and body:

```typescript
export async function buildDossier(
  topic: string,
  opts: { enrich: boolean; use_llm: boolean; use_prefs?: boolean },
  signal?: AbortSignal,
): Promise<BuildResponse> {
  const res = await fetch("/api/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, enrich: opts.enrich, use_llm: opts.use_llm, use_prefs: opts.use_prefs ?? true }),
    signal,
  })
  const data = (await res.json().catch(() => null)) as BuildResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}
```

- [ ] **Step 2: Add rehearsal props to `DossierView.tsx`** (the read-only view is unchanged when props are absent)

Replace the `Claim`, `Section`, and `DossierView` function signatures/bodies with these (other helpers `StatusMark`, `FigureCard` unchanged):

```tsx
export type ClaimMark = "wrong" | "important"

interface Rehearsal {
  rehearsal?: boolean
  markOf?: (heading: string, claim: DossierClaim) => ClaimMark | null
  onMark?: (heading: string, claim: DossierClaim, mark: ClaimMark) => void
  onMissing?: (heading: string, text: string) => void
}

function Claim({ claim, heading, r }: { claim: DossierClaim; heading: string; r: Rehearsal }) {
  const active = r.markOf?.(heading, claim) ?? null
  return (
    <li className="flex gap-3">
      <StatusMark status={claim.status} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="reading !text-[0.98rem] !leading-snug">{claim.text}</span>
          {claim.figure_ids.map((fid) => (
            <a key={fid} href={`#${fid}`}
               className="border-2 border-border bg-primary px-1.5 font-mono text-[10px] font-bold text-primary-foreground">
              {fid}
            </a>
          ))}
        </div>
        {claim.why && (
          <p className="mt-1.5 border-l-2 border-border pl-3 font-serif text-sm leading-relaxed text-muted-foreground">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Why</span>{" "}
            {claim.why}
          </p>
        )}
        {claim.sub_items.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1">
            {claim.sub_items.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                <span className="mt-0.5 select-none font-mono text-muted-foreground">☐</span>
                <span className="font-serif leading-relaxed">{s}</span>
              </li>
            ))}
          </ul>
        )}
        {r.rehearsal && (
          <div className="mt-2 flex gap-2">
            <button type="button" onClick={() => r.onMark?.(heading, claim, "wrong")}
              className={`border-2 border-border px-2 py-0.5 font-mono text-[11px] ${active === "wrong" ? "bg-destructive text-destructive-foreground" : "bg-card text-muted-foreground"}`}>
              ✗ wrong
            </button>
            <button type="button" onClick={() => r.onMark?.(heading, claim, "important")}
              className={`border-2 border-border px-2 py-0.5 font-mono text-[11px] ${active === "important" ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground"}`}>
              ★ important
            </button>
          </div>
        )}
      </div>
    </li>
  )
}

function MissingInput({ heading, onMissing }: { heading: string; onMissing: (h: string, t: string) => void }) {
  const [text, setText] = useState("")
  return (
    <form className="mt-3 flex gap-2"
      onSubmit={(e) => { e.preventDefault(); const t = text.trim(); if (t) { onMissing(heading, t); setText("") } }}>
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Missing from ${heading}…`}
        className="field flex-1 !py-1.5 text-sm" />
      <button type="submit" className="border-2 border-border bg-secondary px-2 py-1 font-mono text-[11px]">+ missing</button>
    </form>
  )
}

function Section({ section, r }: { section: DossierSection; r: Rehearsal }) {
  return (
    <Card className="p-6">
      <h2 className="font-display text-xl font-bold text-foreground">{section.heading}</h2>
      {section.intro && <p className="mt-1 text-sm text-muted-foreground">{section.intro}</p>}
      {section.claims.length > 0 && (
        <ul className="mt-5 flex flex-col gap-4">
          {section.claims.map((c, i) => (
            <Claim key={i} claim={c} heading={section.heading} r={r} />
          ))}
        </ul>
      )}
      {r.rehearsal && r.onMissing && <MissingInput heading={section.heading} onMissing={r.onMissing} />}
      {section.figures.length > 0 && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {section.figures.map((f) => (<FigureCard key={f.fig_id} fig={f} />))}
        </div>
      )}
    </Card>
  )
}

export default function DossierView({ dossier, ...r }: { dossier: Dossier } & Rehearsal) {
  const appendix = dossier.appendix.entries
  return (
    <div className="flex flex-col gap-5">
      {dossier.sections.map((s, i) => (<Section key={i} section={s} r={r} />))}
      {appendix.length > 0 && (
        <Card className="bg-card p-6">
          <h2 className="eyebrow">Appendix</h2>
          <div className="mt-3 flex flex-col gap-4">
            {appendix.map((e, i) => (
              <div key={i}>
                <h3 className="text-sm font-semibold text-foreground">{e.heading}</h3>
                {e.items.length > 0 && (
                  <ul className="mt-1 ml-5 list-disc font-serif text-sm text-muted-foreground">
                    {e.items.map((it, j) => (<li key={j}>{it}</li>))}
                  </ul>
                )}
                {e.sources.length > 0 && (
                  <ul className="mt-1 ml-5 list-disc font-serif text-sm text-muted-foreground">
                    {e.sources.map((src, j) => (<li key={j}>{src}</li>))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
```
Add the needed imports at the top of `DossierView.tsx`:
```tsx
import { useState } from "react"
```
(Keep the existing `import type { Dossier, DossierClaim, DossierFigure, DossierSection } from "@/lib/api"` and `import { Card } from "@/components/ui"`.)

- [ ] **Step 3: Create `RememberedPanel.tsx`**

```tsx
// web/src/components/build/RememberedPanel.tsx
import { Card } from "@/components/ui"

export default function RememberedPanel({ remembered }: { remembered: number }) {
  return (
    <Card className="bg-secondary p-4 text-sm">
      <p className="font-bold text-foreground">
        Remembered {remembered} operative preference{remembered === 1 ? "" : "s"}.
      </p>
      <p className="mt-1 text-muted-foreground">
        The board below was regenerated with your marks applied. These preferences now carry to future
        boards of the same subspecialty. Decision-support only — verify against primary sources.
      </p>
    </Card>
  )
}
```

- [ ] **Step 4: Wire rehearsal into `Build.tsx`**

Add imports:
```tsx
import { buildDossier, fetchBuildPdf, submitFeedback, type BuildResponse, type FeedbackItemIn, type DossierClaim } from "@/lib/api"
import RememberedPanel from "@/components/build/RememberedPanel"
import type { ClaimMark } from "@/components/build/DossierView"
```
Add state (next to the other `useState`s):
```tsx
  const [rehearsal, setRehearsal] = useState(false)
  const [marks, setMarks] = useState<FeedbackItemIn[]>([])
  const [remembered, setRemembered] = useState<number | null>(null)

  const markKey = (heading: string, claim: DossierClaim) => `${heading}::${claim.text}`
  const markOf = (heading: string, claim: DossierClaim): ClaimMark | null => {
    const m = marks.find((x) => x.text === markKey(heading, claim))
    return m && (m.mark === "wrong" || m.mark === "important") ? m.mark : null
  }
  const onMark = (heading: string, claim: DossierClaim, mark: ClaimMark) =>
    setMarks((prev) => {
      const key = markKey(heading, claim)
      const without = prev.filter((x) => !(x.text === key && (x.mark === "wrong" || x.mark === "important")))
      const had = prev.some((x) => x.text === key && x.mark === mark)
      return had ? without : [...without, { mark, text: claim.text, section: heading }]
    })
  const onMissing = (heading: string, text: string) =>
    setMarks((prev) => [...prev, { mark: "missing", text, section: heading }])

  async function remember() {
    if (resp?.kind !== "dossier" || !marks.length) return
    setRemembered(null)
    const r = await submitFeedback(resp.topic, marks, { enrich, use_llm: useLlm })
    if (r.kind === "dossier") {
      setResp({ kind: "dossier", build_id: resp.build_id, topic: r.topic, dossier: r.dossier })
      setRemembered(r.remembered)
      setMarks([])
    } else {
      setNetError(r.kind === "unavailable" ? r.reason : r.error)
    }
  }
```
Note: `onMark` uses `x.text === key` to find a claim-level wrong/important; because `markKey` embeds the claim text, the value sent to the API as `text` for those marks must be the claim text, not the key. Adjust `onMark` to store the real claim text while de-duping by claim:
```tsx
  const onMark = (heading: string, claim: DossierClaim, mark: ClaimMark) =>
    setMarks((prev) => {
      const isClaim = (x: FeedbackItemIn) => x.section === heading && x.text === claim.text && (x.mark === "wrong" || x.mark === "important")
      const without = prev.filter((x) => !isClaim(x))
      const had = prev.some((x) => isClaim(x) && x.mark === mark)
      return had ? without : [...without, { mark, text: claim.text, section: heading }]
    })
  const markOf = (heading: string, claim: DossierClaim): ClaimMark | null => {
    const m = marks.find((x) => x.section === heading && x.text === claim.text && (x.mark === "wrong" || x.mark === "important"))
    return (m?.mark as ClaimMark) ?? null
  }
```
(Use these corrected `onMark`/`markOf`; drop the `markKey` helper.)

In the `resp.kind === "dossier"` render block, add the rehearsal toggle + submit bar, the remembered panel, and pass the handlers to `DossierView`:
```tsx
      {resp && !loading && resp.kind === "dossier" && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl font-bold text-foreground">{resp.dossier.title}</h2>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" checked={rehearsal} onChange={(e) => setRehearsal(e.target.checked)} className="accent-primary" />
                Rehearsal mode
              </label>
              <Button variant="outline" onClick={() => void onDownloadPdf()} disabled={pdfLoading}>
                {pdfLoading ? "Rendering PDF…" : "Download PDF"}
              </Button>
            </div>
          </div>
          {pdfError && <span className="text-xs text-destructive">{pdfError}</span>}
          {rehearsal && (
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void remember()} disabled={!marks.length}>
                Remember {marks.length || ""} mark{marks.length === 1 ? "" : "s"} &amp; update board
              </Button>
              <span className="text-xs text-muted-foreground">
                Mark claims ✗ wrong / ★ important, or add a missing consideration per section.
              </span>
            </div>
          )}
          {remembered !== null && <RememberedPanel remembered={remembered} />}
          <EvidenceBar summary={resp.dossier.summary} />
          <DossierView dossier={resp.dossier} rehearsal={rehearsal} markOf={markOf} onMark={onMark} onMissing={onMissing} />
        </div>
      )}
```

- [ ] **Step 5: Typecheck + build the web bundle (the gate)**

Run: `cd web && npm install && npm run build`
Expected: `tsc -b` passes (no TS errors) and `vite build` writes `web/dist/` with no errors. Fix any type errors before committing.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/api.ts web/src/components/build/DossierView.tsx \
        web/src/components/build/RememberedPanel.tsx web/src/pages/Build.tsx
git commit -m "feat(rehearsal,web): rehearsal mode — mark the board, remember, re-render updated board"
```

---

### Task 7: End-to-end browser observation + runbook

**Files:** Create `docs/runbooks/2026-06-19-surgeon-in-the-loop.md`; (verification artifact) a Playwright screenshot.

- [ ] **Step 1: Boot the stack and exercise the loop in a real browser**

Run (from the worktree root): `cd web && (npm run dev &)  # api :8001 + vite :5173`
Then with the installed Playwright, drive `/build`: build "C5-6 corpectomy" (use_llm off for a fast offline board), enable **Rehearsal mode**, mark one claim ✗ wrong and one ★ important, add a missing consideration, click **Remember … & update board**. Capture a screenshot to `$CLAUDE_JOB_DIR/tmp/rehearsal.png`.

Expected (observe + record): the board re-renders with the added consideration present, the important claim elevated, the wrong claim de-emphasized; the RememberedPanel shows "Remembered N operative preferences." This is the web-loop's RUN-and-observe gate.

- [ ] **Step 2: Confirm the engine/API loop is green (the automated gate)**

Run: `.loopvenv/bin/python -m pytest -p no:cacheprovider -q tests/test_pipeline.py tests/test_compile.py tests/test_render_md.py tests/test_board_view.py tests/test_topic_extract.py tests/rehearsal`
Expected: PASS — baseline 92 + all new rehearsal/api tests.

- [ ] **Step 3: Write the runbook**

```markdown
# Runbook — Surgeon-in-the-Loop Rehearsal (web)

Closes the gap between "generate a dossier" and a board that learns the surgeon's operative preferences.

## Use it
1. `./dev.sh` (or `cd web && npm run dev`) → http://localhost:5173/build. API on :8001.
2. Build a board (e.g. "C5-6 corpectomy").
3. Toggle **Rehearsal mode**. Mark claims **✗ wrong** / **★ important**; add a **+ missing** consideration per section.
4. Click **Remember … & update board** → `POST /api/feedback`: marks distil into profile-keyed preferences
   (`operative-preferences.json`, override via `CASEBOARD_PREFS_STORE`) and the board regenerates with them.
5. Later builds apply the memory automatically (`/api/build` `use_prefs` defaults on); `GET /api/preferences`
   shows what is remembered (action, pattern, weight, source cases).

## Guardrails (clinical)
- `add`/`important` apply immediately. A single **wrong** only **de-emphasizes** (moves the claim to the end
  of its section); **removal requires reinforcement** (marked wrong on ≥2 cases). Nothing safety-critical is
  silently deleted on one click. Provenance (weight + sources) is visible via `/api/preferences`.
- Memory is keyed by subspecialty **profile** (spine/skull-base/vascular), so it generalizes across cases.
- Decision-support only; verify against primary sources. The interactive surface is the web console; the CLI
  (`caseboard build/case`) and engine are unchanged.
```

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/2026-06-19-surgeon-in-the-loop.md
git commit -m "docs(rehearsal): surgeon-in-the-loop runbook + e2e observation"
```

---

## Self-Review

**1. Spec coverage.**
- mark wrong/missing/important → Task 1 (`MARKS`) + Task 6 (UI controls). ✓
- system updates the board → Tasks 3–5 (apply in build + `/api/feedback` returns the rebuilt board) + Task 6 (re-render). ✓
- remembers reusable operative heuristics (by profile) → Task 2 (`distill`, profile-keyed, reinforced) + persisted store + `/api/preferences`. ✓
- WEB-first surface → Tasks 5–7 (FastAPI + rehearsal-mode Build page + browser observation). ✓
- structured-case front half (paste→extract→board) → already shipped; untouched (default no-op keeps it green). ✓

**2. Placeholder scan.** Every step carries complete, runnable code (engine/API/web). No "TBD"/"handle edge cases"/"similar to Task N". Web correctness is gated by `npm run build` (Task 6 Step 5).

**3. Type consistency.** `apply_preferences(manifest, profile, prefs)`, `distill(feedback, existing)`, `default_store_path()`, `target_file_for_heading(heading)`, `Preference` fields, and the API `_do_build(topic, enrich, use_llm, prefs)` signature are identical across all tasks and tests. Web: `FeedbackItemIn{mark,text,section?,note?}`, `submitFeedback`, `ClaimMark`, and `DossierView` props (`rehearsal/markOf/onMark/onMissing`) match between `api.ts`, `DossierView.tsx`, and `Build.tsx`. ✓

**Implementer notes.** Apply prefs AFTER `prune_offtarget`. Keep `prefs=None`/`use_prefs=False` no-ops (Task 4/5 verify the 92-test baseline). Frozen `QuestionCard`/`QuestionManifest` → build new. Run `cd web && npm install` once before the first web build. Delete the flagged `why-it-matters` marker in `MissingInput`.
