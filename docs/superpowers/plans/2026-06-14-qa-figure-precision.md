# Q&A Figure-Precision Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Apply a high-precision guard subset (`cranial↔spine` + `non-op-angio`) on the Q&A figure path so off-domain plates (e.g. a spine laminoplasty figure in an M1-thrombectomy answer) stop leaking — without touching board behavior and without over-blocking angiographic figures.

**Architecture:** Add a `guards="full"|"strict"` selector to `figure_offtarget`; thread a `guard_set` through `FigureRetriever.retrieve`; Q&A passes the question as the region signal with `guard_set="strict"`. Boards keep the default (`"full"`) and are byte-identical.

**Tech Stack:** Python, pytest. Discipline: fixing-pipeline-output-errors (prove ACTIVE on real data; prove no board collateral).

**Spec:** `docs/superpowers/specs/2026-06-14-qa-figure-precision-design.md`

**Branch:** `qa-figure-precision` (not `master`). Controller creates it before Task 1.

**Baseline:** `master` @ HEAD after spec+plan commits, 287 tests. After: 287 + new unit tests (~7) → ~294.

---

## Task 1: `guards` selector in `figure_offtarget`

**Files:** Modify `neuro_core/figure_guards.py`; Test `tests/neuro_core/test_figure_guards.py` (append).

- [ ] **Step 1: Write failing tests** (append to `tests/neuro_core/test_figure_guards.py`):

```python
from neuro_core.figure_guards import figure_offtarget as _off


def test_strict_blocks_cranial_spine_but_not_diagnostic_or_sellar():
    cranial_q = "middle cerebral artery aneurysm clipping"
    # spine plate on a cranial question -> blocked in BOTH modes
    spine_cap = "Lumbar pedicle screw entry point and trajectory"
    assert _off(spine_cap, cranial_q, book="Benzel Spine", guards="strict") is True
    assert _off(spine_cap, cranial_q, book="Benzel Spine", guards="full") is True

    # angiographic figure whose caption names the modality -> NOT blocked in strict
    # (diagnostic-image is full-only), but IS blocked in full.
    angio_cap = ("CT (computed tomography) angiography and DSA demonstrate the ICA "
                 "and middle cerebral artery aneurysm")
    assert _off(angio_cap, cranial_q, book="Video Atlas", guards="strict") is False
    assert _off(angio_cap, cranial_q, book="Video Atlas", guards="full") is True

    # sellar plate on a non-sellar cranial question -> full-only guard
    sellar_cap = "Transsphenoidal view of the pituitary gland and sella"
    assert _off(sellar_cap, cranial_q, book="Rhoton", guards="strict") is False
    assert _off(sellar_cap, cranial_q, book="Rhoton", guards="full") is True


def test_strict_blocks_nonop_angio_positioning():
    cap = "View positioning for the Haughton angiographic projection at 30 frames per second"
    assert _off(cap, "carotid stenting", guards="strict") is True


def test_full_default_unchanged_signature():
    # default is full
    assert _off("Lumbar pedicle screw", "mca aneurysm", book="Benzel Spine") is True
```

- [ ] **Step 2: Run — expect FAIL** (`guards` kwarg unknown / strict not honored)

Run: `python3 -m pytest tests/neuro_core/test_figure_guards.py -q`
Expected: the new tests FAIL (`TypeError: figure_offtarget() got an unexpected keyword argument 'guards'`).

- [ ] **Step 3: Implement** — three edits in `neuro_core/figure_guards.py`:

(a) Signature (line ~145):
```python
def figure_offtarget(caption: str, topic: str, book: str = "", context: str = "",
                     *, guards: str = "full") -> bool:
```

(b) Gate the diagnostic-image check (the `_DIAGNOSTIC_IMAGE` block) behind full:
```python
    if guards == "full" and any(x in cap for x in _DIAGNOSTIC_IMAGE):
        return True                          # diagnostic scan, not operative atlas anatomy
```

(c) After the two cranial↔spine `return True` branches (right before the
`# peripheral-nerve/brachial-plexus` comment), insert the strict early-out:
```python
    if guards != "full":
        return False                         # strict (Q&A): cranial<->spine + non-op-angio only
```
Everything below (peripheral-nerve, sellar, anterior↔posterior-fossa, spine level/CVJ) thus runs
only in `"full"` mode. `_NONOP_ANGIO` stays above (runs in both).

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/neuro_core/test_figure_guards.py -q`
Expected: all pass (existing + 3 new).

- [ ] **Step 5: Commit**
```bash
git add neuro_core/figure_guards.py tests/neuro_core/test_figure_guards.py
git commit -m "feat(guards): add strict guard subset (cranial<->spine + non-op-angio) for Q&A"
```

---

## Task 2: thread `guard_set` through `FigureRetriever.retrieve`

**Files:** Modify `neuro_core/figure_retriever.py`; Test `tests/neuro_core/test_figure_retriever.py` (append).

- [ ] **Step 1: Write failing test** (append):

```python
import neuro_core.figure_retriever as _fr


def test_retrieve_threads_guard_set_to_offtarget(monkeypatch):
    seen = {}

    def fake_off(caption, topic, book="", context="", *, guards="full"):
        seen["guards"] = guards
        return False

    monkeypatch.setattr(_fr, "figure_offtarget", fake_off)
    rows = [{"book": "Rhoton", "page": 1, "figure_path": "/x/p1.png",
             "caption": "middle cerebral artery aneurysm", "context": ""}]
    r = _fr.FigureRetriever(rows)
    r.retrieve("middle cerebral artery aneurysm", topic="mca aneurysm", guard_set="strict")
    assert seen["guards"] == "strict"
    seen.clear()
    r.retrieve("middle cerebral artery aneurysm", topic="mca aneurysm")  # default
    assert seen["guards"] == "full"
```

- [ ] **Step 2: Run — expect FAIL** (`retrieve()` rejects `guard_set`, or guards stays "full")

Run: `python3 -m pytest tests/neuro_core/test_figure_retriever.py -q`
Expected: FAIL (`unexpected keyword argument 'guard_set'`).

- [ ] **Step 3: Implement** — in `neuro_core/figure_retriever.py`, edit `retrieve`:
```python
    def retrieve(self, query, *, topic: str = "", top_n: int = 8, guard_set: str = "full"):
        qterms = _expand_terms(set(_cap_toks(query)))
        if not qterms:
            return []
        if topic:
            candidates = [r for r in self._rows
                          if not figure_offtarget(r["caption"], topic, r.get("book", ""),
                                                  r.get("context", ""), guards=guard_set)]
        else:
            candidates = list(self._rows)
```
(Rest of the method unchanged.)

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/neuro_core/test_figure_retriever.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**
```bash
git add neuro_core/figure_retriever.py tests/neuro_core/test_figure_retriever.py
git commit -m "feat(figret): thread guard_set through retrieve (default full = boards unchanged)"
```

---

## Task 3: Q&A path passes the question as region + strict guards

**Files:** Modify `neuro_core/query.py`; Test `tests/neuro_core/test_query_caption_hits.py` (create).

- [ ] **Step 1: Write failing test** (create `tests/neuro_core/test_query_caption_hits.py`):

```python
from neuro_core.query import Engine


class _Cfg:
    caption_retrieval = True
    caption_retrieve_k = 8


class _FakeCapIdx:
    def __init__(self):
        self.kw = None

    def retrieve(self, query, *, topic="", top_n=8, guard_set="full"):
        self.kw = dict(query=query, topic=topic, top_n=top_n, guard_set=guard_set)
        return []


def test_caption_hits_passes_question_as_topic_and_strict_guards():
    idx = _FakeCapIdx()
    eng = Engine(_Cfg(), None, None, None, None, caption_index=idx)
    q = "structures at risk clipping an MCA bifurcation aneurysm"
    eng._caption_hits(q)
    assert idx.kw["topic"] == q
    assert idx.kw["guard_set"] == "strict"
    assert idx.kw["query"] == q
```

- [ ] **Step 2: Run — expect FAIL** (current call uses `topic=""`, no `guard_set`)

Run: `python3 -m pytest tests/neuro_core/test_query_caption_hits.py -q`
Expected: FAIL on the `topic`/`guard_set` assertions (and/or `retrieve()` got unexpected `guard_set` before Task 2 — but Task 2 is merged first, so it's the assertion that fails).

- [ ] **Step 3: Implement** — in `neuro_core/query.py::_caption_hits`, change the retrieve call from:
```python
            hits = self.caption_index.retrieve(question, topic="",
                                               top_n=self.config.caption_retrieve_k)
```
to:
```python
            hits = self.caption_index.retrieve(question, topic=question,
                                               top_n=self.config.caption_retrieve_k,
                                               guard_set="strict")
```

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/neuro_core/test_query_caption_hits.py -q`
Expected: pass.

- [ ] **Step 5: Commit**
```bash
git add neuro_core/query.py tests/neuro_core/test_query_caption_hits.py
git commit -m "feat(qa): Q&A figure lane passes question as region + strict guards"
```

---

## Task 4: Real-data validation + board parity + acceptance

**Files:** none committed (a throwaway validation script in `/home/michael/.claude/jobs/ecc632c3/tmp/`).

- [ ] **Step 1: Full unit suite**

Run: `python3 -m pytest -q`
Expected: all pass (~294; baseline 287 + new unit tests).

- [ ] **Step 2: Prove ACTIVE on real data (the leak is gone, angio survives)**

Write `/home/michael/.claude/jobs/ecc632c3/tmp/qa_fig_check.py`:
```python
from neuro_core.query import query
qs = [
    "In mechanical thrombectomy for an acute M1 MCA occlusion, how do stent-retriever and "
    "direct aspiration (ADAPT) techniques compare, and key technical steps?",
    "For flow-diverter (Pipeline) treatment of an ICA aneurysm, what is the antiplatelet "
    "management and major complications?",
]
for q in qs:
    r = query(q, force=True)
    print(f"\n=== {q[:60]}... ===")
    for f in r.figures:
        print(f"  {f.book} p.{f.page} :: {f.caption[:90]}")
```
Run: `cd /home/michael/projects/neuro-caseboard && python3 /home/michael/.claude/jobs/ecc632c3/tmp/qa_fig_check.py 2>/dev/null`
Expected (manual/blind check): **no spine plate** in the thrombectomy figures; **angiographic
(CT/CTA/DSA) figures still present** in both (NOT over-blocked). If angio figures vanished →
diagnostic-image leaked into strict → STOP and fix Task 1.

- [ ] **Step 3: Prove NO board collateral**

Re-run the board figure evaluation exactly as the repo defines it and confirm the MCA/CPA/C1-C2
figure result is unchanged from `master`.
Run: `cd /home/michael/projects/neuro-caseboard && python3 -m pytest tests/ -q -k figure` (and any
repo `figure_eval` entry point under `eval/`). Expected: unchanged / green.

- [ ] **Step 4: Hand off** — REQUIRED SUB-SKILL: superpowers:finishing-a-development-branch for
`qa-figure-precision`.

---

## Self-Review (controller)
- **Spec coverage:** §3.1 → Task 1; §3.2 → Task 2; §3.3 → Task 3; §4 acceptance → Task 4.
- **Type consistency:** `figure_offtarget(..., *, guards="full")`, `retrieve(..., guard_set="full")`,
  and the `_caption_hits` call (`topic=question, guard_set="strict"`) match across tasks.
- **Boards unchanged:** every new param defaults to the full/board behavior; verified by Task 4 §3.
- **fixing-pipeline-output-errors:** Task 4 §2 proves the fix is ACTIVE on real data and §3 proves
  no collateral — the two ways this class of fix dies.
