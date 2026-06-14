# Phase 0: Shared Core (neuro_core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge textbook-rag into the neuro-caseboard repo as an importable `neuro_core` package, collapse the two figure-caption retrievers into one (guards optional/topic-aware), and delete the `sys.path` glue — with behavior unchanged, proven by the existing test suites.

**Architecture:** Monorepo rooted in neuro-caseboard. textbook-rag's `engine/` becomes `neuro_core/`; its `cli/`+`server/`+`app/` become `qa/`. Both the Q&A engine and the board pipeline import one `neuro_core.figure_retriever.FigureRetriever`; guards run only when a `topic` is passed (boards), off for free-text Q&A.

**Tech Stack:** Python 3.10+, LanceDB, PyMuPDF, FastAPI/Streamlit (qa surface), pytest, git subtree.

**Reference spec:** `docs/superpowers/specs/2026-06-14-caseboard-textbookrag-integration-design.md`

**Conventions for every task:** run from the caseboard repo root `/home/michael/projects/neuro-caseboard` unless stated. The large `index/` and `assets/` dirs are NOT committed (already gitignored); set `TEXTBOOK_INDEX_DIR=/home/michael/neuro-textbook-rag/index` and `ASSETS_DIR=/home/michael/neuro-textbook-rag/assets/figures` in the env (or `.env`) so the moved code finds existing data.

---

### Task 1: Safety net — branch + baseline counts

**Files:** none (git + verification only)

- [ ] **Step 1: Create the integration branch**

```bash
cd /home/michael/projects/neuro-caseboard
git checkout -b phase0-shared-core
```

- [ ] **Step 2: Record the caseboard baseline test count**

Run: `python3 -m pytest -q | tail -2`
Expected: `178 passed`

- [ ] **Step 3: Record the textbook-rag baseline test count**

Run: `cd /home/michael/neuro-textbook-rag && python3 -m pytest -q | tail -2 && cd -`
Expected: `112 passed`

- [ ] **Step 4: Confirm textbook-rag working tree is committed (subtree needs a clean ref)**

Run: `git -C /home/michael/neuro-textbook-rag status --short`
Expected: empty (HEAD is `3811efc`). If not, commit there first.

---

### Task 2: Import textbook-rag with history via git subtree

**Files:**
- Create: `_tbimport/` (temporary staging dir, removed in Task 3)

- [ ] **Step 1: Add the local textbook-rag repo as a remote**

```bash
git remote add textbookrag /home/michael/neuro-textbook-rag
git fetch textbookrag
```

- [ ] **Step 2: Subtree-import its branch under a staging prefix (preserves history)**

```bash
git subtree add --prefix=_tbimport textbookrag local-quantized-synthesis
```
Expected: "Added dir '_tbimport'" and a merge commit.

- [ ] **Step 3: Verify the tree landed**

Run: `ls _tbimport/engine _tbimport/cli _tbimport/server _tbimport/app`
Expected: the engine/cli/server/app files are present.

---

### Task 3: Reshape into neuro_core/ + qa/ and drop the staging dir

**Files:**
- Move: `_tbimport/engine/*` → `neuro_core/`
- Move: `_tbimport/scripts/*` → `neuro_core/scripts/`
- Move: `_tbimport/cli`, `_tbimport/server`, `_tbimport/app` → `qa/cli`, `qa/server`, `qa/app`
- Move: `_tbimport/eval/*` → `eval/textbook/` ; `_tbimport/tests/*` → `tests/neuro_core/`
- Delete: `_tbimport/` and its stray `.claude/worktrees/` copy (do NOT migrate the worktree)

- [ ] **Step 1: Create target dirs and move the engine + scripts**

```bash
mkdir -p neuro_core/scripts qa eval/textbook tests/neuro_core
git mv _tbimport/engine/*.py neuro_core/
git mv _tbimport/scripts/*.py neuro_core/scripts/
touch neuro_core/__init__.py neuro_core/scripts/__init__.py qa/__init__.py
```

- [ ] **Step 2: Move the Q&A surfaces and eval/tests**

```bash
git mv _tbimport/cli qa/cli
git mv _tbimport/server qa/server
git mv _tbimport/app qa/app
git mv _tbimport/eval/*.py eval/textbook/ 2>/dev/null || true
git mv _tbimport/tests/*.py tests/neuro_core/ 2>/dev/null || true
```

- [ ] **Step 3: Remove everything else from staging (worktrees, README dupes, data stubs)**

```bash
rm -rf _tbimport
```

- [ ] **Step 4: Verify no staging dir remains and neuro_core has the engine modules**

Run: `test ! -e _tbimport && ls neuro_core/index.py neuro_core/query.py neuro_core/figures.py neuro_core/caption_index.py`
Expected: all four paths print (no error).

- [ ] **Step 5: Commit the reshape**

```bash
git add -A
git commit -m "refactor(core): import textbook-rag as neuro_core/ + qa/ (subtree, history preserved)"
```

---

### Task 4: Repoint `engine.*` imports to `neuro_core.*` and package it

**Files:**
- Modify: every moved file under `neuro_core/`, `qa/`, `eval/textbook/`, `tests/neuro_core/` that imports `engine`
- Modify: `pyproject.toml` (add `neuro_core*`, `qa*` to packages)

- [ ] **Step 1: Rewrite intra-core imports (`from engine` / `import engine` → `neuro_core`)**

```bash
grep -rl "engine" --include=*.py neuro_core qa eval/textbook tests/neuro_core \
  | xargs sed -i -E 's/\bfrom engine\./from neuro_core./g; s/\bfrom engine import/from neuro_core import/g; s/\bimport engine\b/import neuro_core/g'
```

- [ ] **Step 2: Verify no `engine.`-style imports remain in the moved tree**

Run: `grep -rn "from engine\|import engine" --include=*.py neuro_core qa eval/textbook tests/neuro_core || echo CLEAN`
Expected: `CLEAN`

- [ ] **Step 3: Add the new packages to setuptools discovery**

In `pyproject.toml`, replace the `[tool.setuptools.packages.find]` include list:
```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["neuro_caseboard*", "neuro_core*", "qa*"]
```

- [ ] **Step 4: Verify neuro_core imports cleanly (no env, no sys.path hack)**

Run: `python3 -c "import neuro_core.index, neuro_core.query, neuro_core.caption_index, neuro_core.figures; print('core OK')"`
Expected: `core OK`

- [ ] **Step 5: Run the moved textbook-rag tests in their new home**

Run: `python3 -m pytest -q tests/neuro_core | tail -2`
Expected: `112 passed` (same count as the Task 1 baseline)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(core): repoint engine.* imports to neuro_core.* and package it"
```

---

### Task 5: Build the unified figure lane in neuro_core (TDD)

This collapses textbook-rag's `CaptionIndex` and caseboard's `FigureCaptionRetriever` into one
`FigureRetriever` whose guards run only when a `topic` is supplied.

**Files:**
- Create: `neuro_core/figure_guards.py`
- Create: `neuro_core/figure_retriever.py`
- Create: `tests/neuro_core/test_figure_retriever.py`

- [ ] **Step 1: Move the guard logic verbatim into `figure_guards.py`**

Cut these symbols verbatim from `neuro_caseboard/retrieve.py` into a new
`neuro_core/figure_guards.py` (keep their bodies byte-for-byte; only relocate):
`_CRANIAL_SIG, _SPINE_SIG, _LEVELS, _BLOCK_LEVELS, _CVJ_TERMS, _SUBAXIAL_TERMS,
_PERIPHERAL_NERVE, _SELLAR, _POSTERIOR_FOSSA, _ANTERIOR_CIRC, _NONOP_ANGIO,
_DIAGNOSTIC_BOOKS, _DIAGNOSTIC_IMAGE, _VIGNETTE, _FLOWCHART, _SPINE_BOOKS, _CRANIAL_BOOKS,
_caption_head, _cap_toks, _levels_in, _expand_terms, _SYNONYMS, _figure_offtarget`.
Add at the top:
```python
import collections
import math
import re
```
Rename the private `_figure_offtarget` to a public `figure_offtarget` (keep a module alias
`_figure_offtarget = figure_offtarget` so existing caseboard tests importing the old name still pass).

- [ ] **Step 2: Write the failing test for the unified retriever**

```python
# tests/neuro_core/test_figure_retriever.py
from neuro_core.figure_retriever import FigureRetriever

ROWS = [
    {"book": "Rhoton", "page": 162, "figure_path": "/x/p162.png", "context": "",
     "caption": "MCA middle cerebral artery bifurcation aneurysm with M1 and M2 trunks"},
    {"book": "Benzel", "page": 516, "figure_path": "/x/p516.png", "context": "",
     "caption": "Lumbar pedicle screw entry point and trajectory"},
    {"book": "Rhoton", "page": 538, "figure_path": "/x/p538.png", "context": "",
     "caption": "AICA passes between the facial and vestibulocochlear nerves in the CPA"},
]

def test_topic_off_skips_guards_topic_on_applies_them():
    r = FigureRetriever(ROWS)
    q = "MCA bifurcation middle cerebral artery"
    # guards OFF (free-text Q&A, topic=""): the MCA plate ranks first
    no_topic = [h.figure_path for h in r.retrieve(q, topic="", top_n=3)]
    assert no_topic and no_topic[0] == "/x/p162.png"
    # guards ON for a spine case: the cranial MCA plate is blocked entirely
    spine = [h.figure_path for h in r.retrieve(
        "C1 C2 pedicle screw", topic="atlantoaxial C1 C2 fixation odontoid", top_n=3)]
    assert "/x/p162.png" not in spine and "/x/p538.png" not in spine

def test_anterior_posterior_guard_only_with_topic():
    r = FigureRetriever(ROWS)
    # CPA topic: the anterior-circulation MCA plate is guarded out
    cpa = [h.figure_path for h in r.retrieve(
        "AICA facial vestibulocochlear", topic="retrosigmoid cerebellopontine angle schwannoma",
        top_n=3)]
    assert "/x/p538.png" in cpa and "/x/p162.png" not in cpa
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python3 -m pytest -q tests/neuro_core/test_figure_retriever.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_core.figure_retriever'`

- [ ] **Step 4: Implement `neuro_core/figure_retriever.py`**

```python
"""Unified figure-retrieval lane: one IDF caption-lexical ranker (prefers the Gemini
caption) + an optional BiomedCLIP semantic lane (RRF-fused), with region/level/domain
guards applied ONLY when a topic is supplied (boards) and skipped for free-text Q&A."""
from __future__ import annotations

import collections
import math
import os
from dataclasses import dataclass, field

from neuro_core.figure_guards import (
    _cap_toks, _caption_head, _expand_terms, _VIGNETTE, _FLOWCHART, figure_offtarget,
    _DIAGNOSTIC_BOOKS,
)


@dataclass
class FigureHit:
    book: str
    page: int
    figure_path: str
    caption: str
    score: float = 0.0
    chapter: str | None = None
    context: str = ""
    vector: object = None


def _fuse(lex, sem, top_n, *, k: int = 60):
    scores: dict = {}
    rowmap: dict = {}
    for rank, (_s, row) in enumerate(lex):
        key = row["figure_path"]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        rowmap[key] = row
    for rank, (_s, row) in enumerate(sem):
        key = row["figure_path"]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        rowmap[key] = row
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(rowmap[key], sc) for key, sc in ranked[:top_n]]


class FigureRetriever:
    def __init__(self, rows, *, embed_fn=None):
        self._rows = rows
        self._embed_fn = embed_fn
        df = collections.Counter()
        for row in rows:
            for t in set(_cap_toks(row["caption"])):
                df[t] += 1
        self._df = df
        self._n = max(1, len(rows))
        self.caption_by_path = {r["figure_path"]: r["caption"] for r in rows}

    def _idf(self, t: str) -> float:
        return math.log((self._n + 1) / (self._df.get(t, 0) + 1))

    def _lexical(self, qterms, candidates):
        scored = []
        for row in candidates:
            ct = collections.Counter(_cap_toks(row["caption"]))
            matched = [t for t in qterms if t in ct]
            if len(matched) < 2:
                continue
            s = sum(ct[t] * self._idf(t) for t in matched)
            cap_low = row["caption"].lower()
            if _VIGNETTE.search(row["caption"]):
                s *= 0.4
            if any(f in cap_low for f in _FLOWCHART):
                s *= 0.35
            if s > 0:
                scored.append((s, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _semantic(self, query, candidates):
        if not self._embed_fn:
            return []
        try:
            import numpy as np
            qv = np.asarray(self._embed_fn(query), dtype="float32").ravel()
        except Exception:
            return []
        qn = float(np.linalg.norm(qv)) or 1.0
        sims = []
        for row in candidates:
            v = row.get("vector")
            if v is None:
                continue
            v = np.asarray(v, dtype="float32").ravel()
            if v.size != qv.size:
                continue
            vn = float(np.linalg.norm(v)) or 1.0
            sims.append((float(qv @ v) / (qn * vn), row))
        sims.sort(key=lambda x: x[0], reverse=True)
        return sims

    def retrieve(self, query, *, topic: str = "", top_n: int = 8):
        qterms = _expand_terms(set(_cap_toks(query)))
        if not qterms:
            return []
        # guards run ONLY when a topic is supplied (boards); Q&A passes topic="" -> no guards
        if topic:
            candidates = [r for r in self._rows
                          if not figure_offtarget(r["caption"], topic, r.get("book", ""),
                                                  r.get("context", ""))]
        else:
            candidates = list(self._rows)
        lex = self._lexical(qterms, candidates)
        sem = self._semantic(query, candidates)
        ordered = _fuse(lex, sem, top_n) if sem else [(row, s) for s, row in lex[:top_n]]
        return [FigureHit(book=row.get("book", ""), page=row.get("page"),
                          figure_path=row["figure_path"], caption=row["caption"],
                          chapter=row.get("chapter"), context=row.get("context", ""),
                          vector=row.get("vector"), score=round(float(s), 4))
                for row, s in ordered]


_ROWS_CACHE = None


def _load_rows(index_dir=None):
    """Load figure rows (book/page/figure_path/effective caption/context/vector) from
    figures.lance once. Effective caption = gemini_caption if present else source caption,
    capped (gemini larger, source tighter). Diagnostic books are skipped."""
    global _ROWS_CACHE
    if _ROWS_CACHE is not None:
        return _ROWS_CACHE
    from neuro_core.config import load_config
    index_dir = index_dir or str(load_config().index_dir)
    rows_out = []
    if os.path.isdir(index_dir):
        import lancedb
        db = lancedb.connect(index_dir)
        names = set(db.table_names())
        if "figures" in names:
            for r in db.open_table("figures").search().limit(10**6).to_list():
                fp = r.get("figure_path") or ""
                book = r.get("book") or ""
                if any(d in book.lower() for d in _DIAGNOSTIC_BOOKS):
                    continue
                gem = (r.get("gemini_caption") or "").strip()
                cap = _caption_head(gem, 700) if gem else _caption_head((r.get("caption") or "").strip())
                if cap and fp and os.path.isfile(fp):
                    rows_out.append({"book": book, "page": r.get("page"), "figure_path": fp,
                                     "caption": cap, "context": "", "vector": r.get("vector")})
            if rows_out and "chunks" in names:
                ctx = {}
                for r in db.open_table("chunks").search().limit(10**6).to_list():
                    t = (r.get("text") or "").strip()
                    if t:
                        kk = (r.get("book") or "", str(r.get("page")))
                        ctx[kk] = (ctx.get(kk, "") + " " + t)[:6000]
                for row in rows_out:
                    row["context"] = ctx.get((row["book"], str(row["page"])), "")
    _ROWS_CACHE = rows_out
    return rows_out


def build_figure_retriever(index_dir=None, *, embed_fn=None):
    rows = _load_rows(index_dir)
    if not rows:
        return None
    return FigureRetriever(rows, embed_fn=embed_fn)
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python3 -m pytest -q tests/neuro_core/test_figure_retriever.py`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add neuro_core/figure_guards.py neuro_core/figure_retriever.py tests/neuro_core/test_figure_retriever.py
git commit -m "feat(core): unified FigureRetriever (guards optional/topic-aware) + figure_guards"
```

---

### Task 6: Point the Q&A engine at the unified retriever

Replace the `CaptionIndex` usage in `neuro_core/query.py` with the unified `FigureRetriever`
(guards off). The text + visual lanes are unchanged.

**Files:**
- Modify: `neuro_core/query.py`
- Delete: `neuro_core/caption_index.py` and its test (superseded)
- Modify: `tests/neuro_core/test_caption_index.py` → fold the still-relevant cases into the new test, then remove the file

- [ ] **Step 1: Add a thin adapter to FigureHit→Hit in `neuro_core/query.py`**

In `neuro_core/query.py`, replace the `from neuro_core.caption_index import CaptionIndex`
import with:
```python
from neuro_core.figure_retriever import build_figure_retriever
from neuro_core.index import Hit
```
Replace `self.caption_index = caption_index` usage: in `_caption_hits`, build/keep a cached
`FigureRetriever` and adapt:
```python
    def _caption_hits(self, question):
        if self.caption_index is None or not getattr(self.config, "caption_retrieval", False):
            return []
        try:
            hits = self.caption_index.retrieve(question, topic="",
                                               top_n=self.config.caption_retrieve_k)
        except Exception:
            return []
        return [Hit(id=f"cap-{h.book}-p{h.page}", book=h.book, chapter=h.chapter,
                    page=h.page, text=h.caption, score=h.score, has_figure=True,
                    caption=h.caption, figure_path=h.figure_path) for h in hits]
```
And keep the display override using `self.caption_index.caption_by_path` (FigureRetriever
exposes the same attribute). In `get_engine`, construct
`caption_index = build_figure_retriever(config.index_dir)` instead of `CaptionIndex(...)`.

- [ ] **Step 2: Delete the superseded module**

```bash
git rm neuro_core/caption_index.py tests/neuro_core/test_caption_index.py
```

- [ ] **Step 3: Run the Q&A test suite**

Run: `python3 -m pytest -q tests/neuro_core/test_query.py`
Expected: PASS (all query tests green; they pass a fake caption_index or none)

- [ ] **Step 4: Real-data smoke — figures unchanged for an MCA question**

Run:
```bash
TEXTBOOK_INDEX_DIR=/home/michael/neuro-textbook-rag/index python3 -c "
from neuro_core.query import get_engine; from neuro_core.config import load_config
e=get_engine(load_config()); 
print([f'{f.book} p{f.page}' for f in e.select_figures('MCA bifurcation aneurysm clipping Sylvian M1 M2')])"
```
Expected: operative MCA-bifurcation plates (e.g. `Schmidek and Sweet p1126`) appear, as before.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(qa): Q&A engine uses unified FigureRetriever (guards off); drop CaptionIndex"
```

---

### Task 7: Point caseboard at neuro_core; delete the sys.path glue

**Files:**
- Modify: `neuro_caseboard/retrieve.py`
- Modify: `tests/test_retrieve.py` (imports of moved guard symbols)

- [ ] **Step 1: Replace the textbook lane + figure retriever wiring**

In `neuro_caseboard/retrieve.py`:
- delete `_default_textbook_repo`, `_default_index_dir`'s repo logic, `_index_search_fn`'s
  `sys.path.insert`/`from engine...`/`except: pass`, and the legacy `engine.query.search` block.
- replace the in-process textbook lexical lane with:
```python
from neuro_core.index import Index
from neuro_core.config import load_config

def _index_search_fn(*, index_dir=None):
    index_dir = index_dir or str(load_config().index_dir)
    if not os.path.isdir(index_dir):
        return None
    index = Index(index_dir)
    def search_fn(query, k):
        terms = _SanitizingCorpus._clean(query, 8)
        if not terms:
            return []
        try:
            return [_hit_to_dict(h) for h in (index.text_search(terms, k) or [])]
        except Exception:
            return []
    return search_fn
```
- delete the local `FigureCaptionRetriever`, `_load_figure_rows`, `_build_figure_embed_fn`,
  `_fuse_rankings`, and all guard symbols (now in `neuro_core.figure_guards`).
- replace `build_figure_retriever` with an adapter over the core retriever:
```python
from neuro_core.figure_retriever import build_figure_retriever as _core_build_figret

class _BoardFigRetriever:
    def __init__(self, core):
        self._core = core
    def retrieve(self, query, *, topic="", subdomain=None, top_n=3):
        from caseprep.core.contracts import EvidenceRecord
        from neuro_caseboard.captions import assemble_caption
        out = []
        for h in self._core.retrieve(query, topic=topic, top_n=top_n):
            cap = assemble_caption(h.caption, [])
            cite = f"{h.book}, p.{h.page}" if h.book else ""
            out.append(EvidenceRecord(
                id=f"fig-{h.book}-p{h.page}", source="textbook",
                title=f"{h.book} (p.{h.page})", text=cap,
                metadata={"figure_path": h.figure_path, "caption": cap, "citation": cite,
                          "book": h.book, "page": h.page, "score": h.score,
                          "retrieval_source": "textbook_figcap"}))
        return out

def build_figure_retriever(*, index_dir=None):
    core = _core_build_figret(index_dir)
    return _BoardFigRetriever(core) if core else None
```

- [ ] **Step 2: Repoint guard-symbol imports in the caseboard test**

In `tests/test_retrieve.py`, change imports of `_figure_offtarget`, `_row_caption`, etc. that
moved: `from neuro_caseboard.retrieve import _figure_offtarget` →
`from neuro_core.figure_guards import figure_offtarget as _figure_offtarget`. Keep
`FigureCaptionRetriever`-specific tests only if the class still exists; otherwise port the two
ranking/guard assertions to `neuro_core.figure_retriever.FigureRetriever` (same inputs).

- [ ] **Step 3: Verify the glue is gone**

Run: `grep -rn "sys.path.insert\|from engine\|TEXTBOOK_RAG_REPO" --include=*.py neuro_caseboard || echo CLEAN`
Expected: `CLEAN`

- [ ] **Step 4: Run the caseboard suite**

Run: `python3 -m pytest -q tests/test_retrieve.py | tail -2`
Expected: PASS (count may shift as guard tests move to `tests/neuro_core/`; net coverage preserved)

- [ ] **Step 5: Real-data smoke — the board figure lane still surfaces the MCA bullseye**

Run:
```bash
CASEPREP_TEXTBOOK=1 CASEBOARD_TEXTBOOK_FIGURES=1 \
TEXTBOOK_INDEX_DIR=/home/michael/neuro-textbook-rag/index \
python3 eval/figure_eval.py 2>/dev/null | sed -n '/## mca-bifurcation-clip/,/## c1c2/p' | grep -c "p.1126"
```
Expected: `1` (Schmidek p1126 still present — figure_eval result unchanged)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(boards): caseboard figure lane uses neuro_core; delete sys.path glue"
```

---

### Task 8: Unify config (remove caseboard textbook env vars)

**Files:**
- Modify: `neuro_caseboard/retrieve.py` (any residual `TEXTBOOK_INDEX_DIR` reads → `neuro_core.config`)
- Modify: `README.md` / `pyproject.toml` comment (drop the "editable sibling install" note)

- [ ] **Step 1: Route index path through neuro_core.config**

Ensure caseboard reads the index location from `neuro_core.config.load_config().index_dir`
(honoring its `INDEX_DIR`/env), not a caseboard-specific `TEXTBOOK_INDEX_DIR`. Keep the
board-specific `CASEPREP_TEXTBOOK` / `CASEBOARD_*` flags as-is.

- [ ] **Step 2: Update the stale pyproject comment**

In `pyproject.toml`, replace the "consumed as editable sibling installs" comment block with:
```toml
# neuro_core (the retrieval/figure engine, formerly textbook-rag) now lives in this repo and is
# imported directly. caseprep remains an external editable install:  pip install -e ../caseprep
```

- [ ] **Step 3: Verify caseboard imports with no textbook env vars set**

Run: `env -u TEXTBOOK_RAG_REPO -u TEXTBOOK_INDEX_DIR python3 -c "import neuro_caseboard.retrieve; print('caseboard OK')"`
Expected: `caseboard OK`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(config): single neuro_core.config; drop caseboard textbook env vars"
```

---

### Task 9: Full acceptance + cleanup

**Files:** none (verification only)

- [ ] **Step 1: Run the entire merged suite**

Run: `python3 -m pytest -q | tail -3`
Expected: green; total ≈ 178 + 112 (minus the few caption_index tests folded into the unified test). Record the number.

- [ ] **Step 2: Static integration checks**

Run:
```bash
echo "glue:"; grep -rn "sys.path.insert\|from engine" --include=*.py neuro_caseboard neuro_core qa || echo CLEAN
echo "one retriever class:"; grep -rln "class FigureRetriever\|class FigureCaptionRetriever\|class CaptionIndex" --include=*.py . | grep -v docs
```
Expected: `CLEAN`; exactly one file (`neuro_core/figure_retriever.py`).

- [ ] **Step 3: figure_eval parity (the shipped after-guards result)**

Run:
```bash
CASEPREP_TEXTBOOK=1 CASEBOARD_TEXTBOOK_FIGURES=1 \
TEXTBOOK_INDEX_DIR=/home/michael/neuro-textbook-rag/index python3 eval/figure_eval.py 2>/dev/null \
  | grep -E "p.1126|p.134|p.133|p.150" | sort -u
```
Expected: contains `p.1126` and `p.134`; does NOT contain `p.133` or `p.150` (CPA leak + angio leak still guarded out).

- [ ] **Step 4: Q&A end-to-end smoke**

Run: `TEXTBOOK_INDEX_DIR=/home/michael/neuro-textbook-rag/index python3 -m qa.cli.ask "structures at risk clipping an MCA bifurcation aneurysm"` (CLI prints answer + citations + figure paths)
Expected: a grounded answer with citations and MCA-bifurcation figure paths.

- [ ] **Step 5: Final commit + summary**

```bash
git add -A && git commit -m "chore(phase0): acceptance — merged suite green, one figure lane, glue removed" || echo "nothing to commit"
git log --oneline -10
```

---

## Self-review notes
- **Spec coverage:** §5.2 layout → Tasks 2–4; §5.3 unified lane → Task 5; §5.4 config → Task 8;
  §5.5 glue removal → Task 7; §5.6 subtree migration → Tasks 2–3; §6 acceptance → Task 9. All covered.
- **Out of scope confirmed:** no surface unification (qa/ keeps its CLI/server/app), no caseprep
  changes, no data move — matches spec §9.
- **Known follow-ups (not Phase 0):** the moved `qa/cli`, `qa/server`, `qa/app` keep their own
  entry points; unifying them into one app is Phase 1.
