# Standardize PubMed Augmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make literature augmentation consistent (BACKLOG P2 #7). Today `LiteratureRetriever.retrieve` ranks candidates then returns a bare `records[:k]` — with no quality/relevance floor, so weak queries get **padded** with low-tier off-topic papers, and the user is never told when coverage is thin. Add a **quality floor** (prefer guidelines / trials / systematic reviews / major cohorts; drop case-reports/editorials/untyped padding) and a **coverage note** that explains when only limited literature is available.

**Architecture:** A **pure, hermetically-testable** `neuro_caseboard/literature/standardize.py` — `standardize_records(ranked, *, k, max_tier, tier_fn) -> Augmentation(records, note)` — applied to the already-relevance-ranked records inside `retrieve()`. Relevance still gates ordering (unchanged); the floor only removes low-quality tail-padding and caps at `k`, and emits a note when fewer than `k` quality sources exist. Decoupled from the retriever via an injected `tier_fn` (lazy import avoids a cycle).

**Tech Stack:** Python 3.10+, dataclasses, asyncio (existing test pattern), pytest. Hermetic — the standardizer is pure; the retriever test uses the existing `_FakeClient`.

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_pubmed_augmentation.py`. Full suite ~17min on WSL2; CI runs the full suite.
- **No regression** to existing literature behavior: `tests/test_literature_retriever.py` must still pass. Relevance ordering and the axis fan-out are untouched; we only filter the final slice + expose a note.
- Additive: new module + a minimal change to `retrieve()` (apply filter, set `self.last_coverage_note`). Do NOT change `retrieve()`'s return type (`list[LiteratureRecord]`) — the note is exposed as an instance attribute so existing callers (`qa.build_literature_section`) keep working.
- Verified facts: ranking at `neuro_caseboard/literature/retriever.py:162-170` (returns `records[:self._k]`); `pub_tier(pub_types)` (lower=better: 0 guideline/SR/meta, 1 RCT/trial, 2 cohort/observational/review, 3 untyped, 4 case-report/editorial) at `retriever.py:91`; `LiteratureRecord` has `pub_types: list`; the test fake-client pattern is `_FakeClient` + `asyncio.run(r.retrieve(...))` in `tests/test_literature_retriever.py`.

---

## Tasks (project-loop step cursor)

- [x] Task 1: Pure augmentation standardizer (`neuro_caseboard/literature/standardize.py`) + hermetic unit tests
- [x] Task 2: Apply the floor in `LiteratureRetriever.retrieve` + expose `last_coverage_note` + retriever test

---

### Task 1: Pure augmentation standardizer + hermetic unit tests

**Files:**
- Create: `neuro_caseboard/literature/standardize.py`
- Create (Test): `tests/test_pubmed_augmentation.py`

**Interfaces:**
- Produces:
  - `Augmentation(records: list, note: str)` — dataclass.
  - `standardize_records(ranked: list, *, k: int, max_tier: int = 2, tier_fn=None) -> Augmentation` — keep relevance-ranked records whose `tier_fn(r.pub_types) <= max_tier`, cap at `k`; fallback + note rules below. `tier_fn` defaults (lazy import) to `retriever.pub_tier`.
- Consumes: `pub_tier` (lazy import to avoid a cycle).

**Rules:**
- `quality = [r for r in ranked if tier_fn(r.pub_types) <= max_tier]`; `kept = quality[:k]`.
- note: `""` if `len(kept) >= k`; else if `0 < len(kept) < k` → `"Limited literature: only N source(s) met the evidence bar for this question."`; else if `len(kept) == 0 and ranked` → fallback `kept = ranked[:1]`, note `"No high-quality evidence (guideline, trial, review, or cohort) matched; showing the single most relevant article — interpret with caution."`; else (`not ranked`) → `kept = []`, note `"No relevant literature found for this question."`

**Step 1: Write the failing test** — create `tests/test_pubmed_augmentation.py`:

```python
"""Hermetic unit tests for standardized PubMed augmentation
(neuro_caseboard/literature/standardize.py), BACKLOG P2 #7. Pure — no network/LLM."""
from dataclasses import dataclass, field

from neuro_caseboard.literature.standardize import Augmentation, standardize_records


@dataclass
class _Rec:
    pmid: str
    pub_types: list = field(default_factory=list)


GUIDE = ["Practice Guideline"]
RCT = ["Randomized Controlled Trial"]
COHORT = ["Cohort Study"]      # tier 2 ("cohort")
CASE = ["Case Reports"]        # tier 4
UNTYPED = ["Journal Article"]  # tier 3


def test_drops_low_tier_padding_and_keeps_quality():
    ranked = [_Rec("1", GUIDE), _Rec("2", RCT), _Rec("3", CASE), _Rec("4", UNTYPED)]
    aug = standardize_records(ranked, k=8)
    kept = {r.pmid for r in aug.records}
    assert kept == {"1", "2"}          # guideline + RCT kept; case-report + untyped dropped
    assert "Limited literature" in aug.note


def test_no_note_when_enough_quality():
    ranked = [_Rec(str(i), RCT) for i in range(8)]
    aug = standardize_records(ranked, k=3)
    assert len(aug.records) == 3 and aug.note == ""


def test_fallback_to_single_most_relevant_when_no_quality():
    ranked = [_Rec("1", CASE), _Rec("2", UNTYPED)]
    aug = standardize_records(ranked, k=8)
    assert [r.pmid for r in aug.records] == ["1"]   # most-relevant single, flagged
    assert "interpret with caution" in aug.note


def test_empty_input_explains_no_literature():
    aug = standardize_records([], k=8)
    assert aug.records == [] and "No relevant literature" in aug.note


def test_relevance_order_is_preserved_among_kept():
    ranked = [_Rec("a", RCT), _Rec("b", GUIDE), _Rec("c", COHORT)]
    aug = standardize_records(ranked, k=8)
    assert [r.pmid for r in aug.records] == ["a", "b", "c"]  # order unchanged, all quality
```

**Step 2: Run to verify it fails** — `ModuleNotFoundError: No module named 'neuro_caseboard.literature.standardize'`.

**Step 3: Write the module** — create `neuro_caseboard/literature/standardize.py`:

```python
"""Standardize PubMed augmentation (BACKLOG P2 #7): apply a quality floor to the relevance-ranked
literature pool and explain when coverage is thin — so weak queries are not padded with low-tier
off-topic papers. Pure: no network/LLM. ``tier_fn`` is injected (lazy default) to avoid a cycle."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Augmentation:
    records: list = field(default_factory=list)
    note: str = ""


def standardize_records(ranked: list, *, k: int, max_tier: int = 2, tier_fn=None) -> Augmentation:
    if tier_fn is None:
        from neuro_caseboard.literature.retriever import pub_tier as tier_fn
    quality = [r for r in ranked if tier_fn(getattr(r, "pub_types", [])) <= max_tier]
    kept = quality[:k]
    if kept:
        note = "" if len(kept) >= k else (
            f"Limited literature: only {len(kept)} source(s) met the evidence bar for this question.")
    elif ranked:
        kept = ranked[:1]
        note = ("No high-quality evidence (guideline, trial, review, or cohort) matched; showing the "
                "single most relevant article — interpret with caution.")
    else:
        note = "No relevant literature found for this question."
    return Augmentation(records=kept, note=note)
```

**Step 4: Run to verify it passes** — PASS (5 passed).

**Step 5: Commit**

```bash
git add neuro_caseboard/literature/standardize.py tests/test_pubmed_augmentation.py
git commit -m "loop step 0: pure PubMed augmentation standardizer + hermetic tests (P2 #7)"
```

---

### Task 2: Apply the floor in retrieve() + expose last_coverage_note + retriever test

**Files:**
- Modify: `neuro_caseboard/literature/retriever.py` (`__init__`: `self.last_coverage_note = ""`; end of `retrieve`: apply filter, set note)
- Modify (Test): `tests/test_pubmed_augmentation.py` (append a retriever-integration test using a fake client)

**Edits to `retriever.py`:**

1. Import (top): `from neuro_caseboard.literature.standardize import standardize_records`.
2. `__init__`: add `self.last_coverage_note = ""`.
3. Replace the final two lines of `retrieve`:

```python
        records.sort(key=rank_key)
        aug = standardize_records(records, k=self._k, tier_fn=pub_tier)
        self.last_coverage_note = aug.note
        return aug.records
```

**Step 1: Write the failing test (append to `tests/test_pubmed_augmentation.py`)**

```python
def test_retrieve_applies_quality_floor_and_sets_note():
    """retrieve drops low-tier padding and records a coverage note. Hermetic fake client."""
    import asyncio
    from neuro_caseboard.literature.retriever import LiteratureRetriever

    class _Client:
        async def search(self, query, *, max_results=25, filter_type=None):
            return (["1", "2", "3"], 3)
        async def summaries(self, pmids):
            pt = {"1": ["Practice Guideline"], "2": ["Case Reports"], "3": ["Journal Article"]}
            return [{"pmid": p, "title": f"T{p}", "source": "J", "pubdate": "2023 Jan",
                     "pub_types": pt[p]} for p in ["1", "2", "3"]]
        async def structured_abstracts(self, pmids):
            return {p: {"Results": "x"} for p in ["1", "2", "3"]}
        async def abstracts(self, pmids):
            return {p: "abstract" for p in ["1", "2", "3"]}

    r = LiteratureRetriever(_Client(), k=8, recency_years=7)
    recs = asyncio.run(r.retrieve("subdural hematoma MMA embolization", current_year=2024))
    assert [x.pmid for x in recs] == ["1"]        # only the guideline clears the floor
    assert "Limited literature" in r.last_coverage_note
```

**Step 2-5:** run RED, apply edits, run the full file (expect 6 passed) AND `tests/test_literature_retriever.py` (no regression), commit:

```bash
git add neuro_caseboard/literature/retriever.py tests/test_pubmed_augmentation.py
git commit -m "loop step 1: apply quality floor + coverage note in LiteratureRetriever.retrieve (P2 #7)"
```

---

## Self-Review

**1. Spec coverage:** quality floor (prefer guideline/trial/SR/cohort via `pub_tier<=2`) → no low-tier padding; coverage note explains limited/none; relevance still gates ordering; current-question binding unchanged. ✔
**2. Placeholder scan:** all code/commands runnable + expected output; retriever edit anchors on the existing sort/return. ✔
**3. Type consistency:** `Augmentation(records,note)`, `standardize_records(ranked,*,k,max_tier,tier_fn)` identical across module/tests/retriever; return type of `retrieve` unchanged. ✔

> Follow-up (not this PR): surface `last_coverage_note` through `qa.build_literature_section` → `LiteratureSection` → the Ask "Contemporary Literature" panel so the user reads the limited-literature caveat. This PR lands the floor + note generation.
