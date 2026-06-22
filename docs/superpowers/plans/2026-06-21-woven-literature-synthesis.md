# Woven Literature Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the Ask pathway, produce ONE woven answer synthesized from both textbook passages (`[n]`) and PubMed records (`[L#]`), keeping the two retrievals separate, behind a feature flag, with a light recency tie-breaker and a deterministic precision gate.

**Architecture:** Both lanes retrieve independently (Lane A textbook via `neuro_core`, Lane B PubMed via `neuro_caseboard.literature`). A new `neuro_core` "retrieve-only" seam returns retrieved hits + figures without synthesizing. A new `neuro_caseboard` woven synthesizer takes both sets and emits one answer with two distinct citation namespaces. A new orchestration branch in `qa.answer_question` wires it up when `LITERATURE_WEAVE` is on; otherwise today's separate-block behavior is byte-identical.

**Tech Stack:** Python 3.12, dataclasses, `asyncio`, `concurrent.futures.ThreadPoolExecutor`, pytest. LLM synthesis via the injected `synth_client` (Vertex `gemini-2.5-pro` on this machine).

## Global Constraints

- **Install only `pip install -e .[dev]`** — never `-e ../caseprep` (vendored copy at `vendor/caseprep`).
- **LLM provider is Vertex (OpenRouter optional)** — no first-party LLM-vendor key; never probe one.
- **Tests must be hermetic + scoped.** Fast loop: `pytest tests/neuro_core tests/test_pipeline.py tests/test_retrieve.py tests/test_qa.py` (~20s). Full suite (~17 min) is CI's job. **Never** add `pytest-xdist -n auto`.
- **Guard streamlit imports**: any test importing `streamlit` MUST start with `pytest.importorskip("streamlit")` before the import (web extra absent in required `.[dev]` CI; a bare import aborts the whole run at collection).
- **Tests opt out of dotenv**: `tests/conftest.py` sets `NEURO_CASEBOARD_SKIP_DOTENV=1`; any test touching `load_literature_config` env should set env vars explicitly via `monkeypatch.setenv`.
- **CI gate is pytest only** (no ruff/mypy/eslint gate).
- **Citation namespaces never merge**: textbook uses `[n]`, literature uses `[L#]`, inline and distinct.
- **Refusal string is shared**: `neuro_core.synthesize.REFUSAL == "Not found in the provided sources."` — the woven prompt must emit this verbatim so `is_refusal()` matches.

---

### Task 1: Literature config flags

**Files:**
- Modify: `neuro_caseboard/literature/config.py:63-84`
- Test: `tests/test_literature_config.py`

**Interfaces:**
- Produces: `LiteratureConfig` gains fields `weave: bool`, `recency_boost: int`, `precision_gate: bool`, `precision_min_overlap: int` (all with defaults). `load_literature_config()` reads `LITERATURE_WEAVE` (default off), `LITERATURE_RECENCY_BOOST` (default 0), `LITERATURE_PRECISION_GATE` (default on), `LITERATURE_PRECISION_MIN_OVERLAP` (default 1).

**Design note:** `recency_boost` defaults to **0** (no-op) so flag-off ranking is byte-identical to today — the spec's "modest default" applies only once the A/B justifies a nonzero value. `precision_gate` defaults **on** but is only ever invoked on the woven path (Task 6), so it cannot affect separate-mode behavior.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_literature_config.py`:

```python
def test_woven_flags_defaults(monkeypatch):
    for k in ("LITERATURE_WEAVE", "LITERATURE_RECENCY_BOOST",
              "LITERATURE_PRECISION_GATE", "LITERATURE_PRECISION_MIN_OVERLAP"):
        monkeypatch.delenv(k, raising=False)
    from neuro_caseboard.literature.config import load_literature_config
    cfg = load_literature_config()
    assert cfg.weave is False
    assert cfg.recency_boost == 0
    assert cfg.precision_gate is True
    assert cfg.precision_min_overlap == 1


def test_woven_flags_env_overrides(monkeypatch):
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    monkeypatch.setenv("LITERATURE_RECENCY_BOOST", "2")
    monkeypatch.setenv("LITERATURE_PRECISION_GATE", "off")
    monkeypatch.setenv("LITERATURE_PRECISION_MIN_OVERLAP", "3")
    from neuro_caseboard.literature.config import load_literature_config
    cfg = load_literature_config()
    assert cfg.weave is True
    assert cfg.recency_boost == 2
    assert cfg.precision_gate is False
    assert cfg.precision_min_overlap == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_literature_config.py::test_woven_flags_defaults tests/test_literature_config.py::test_woven_flags_env_overrides -v`
Expected: FAIL with `TypeError` (unexpected fields) or `AttributeError: ... 'weave'`.

- [ ] **Step 3: Write minimal implementation**

In `neuro_caseboard/literature/config.py`, extend the dataclass and loader:

```python
@dataclass(frozen=True)
class LiteratureConfig:
    enabled: bool
    recency_years: int
    k: int
    cache_ttl_days: int
    ncbi_api_key: str
    cache_dir: str
    weave: bool = False
    recency_boost: int = 0
    precision_gate: bool = True
    precision_min_overlap: int = 1
```

In `load_literature_config()`, add to the returned constructor (after `cache_dir=...`):

```python
        weave=_flag(os.environ.get("LITERATURE_WEAVE", "false")),
        recency_boost=int(os.environ.get("LITERATURE_RECENCY_BOOST", "0")),
        precision_gate=_flag(os.environ.get("LITERATURE_PRECISION_GATE", "true")),
        precision_min_overlap=int(os.environ.get("LITERATURE_PRECISION_MIN_OVERLAP", "1")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_literature_config.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/config.py tests/test_literature_config.py
git commit -m "feat(lit): config flags for woven mode, recency boost, precision gate"
```

---

### Task 2: Recency tie-breaker (mechanism B)

**Files:**
- Modify: `neuro_caseboard/literature/retriever.py:116-178`
- Test: `tests/test_literature_retriever.py`

**Interfaces:**
- Consumes: `LiteratureConfig.recency_boost` (Task 1).
- Produces: `LiteratureRetriever.__init__(..., recency_boost: int = 0)`. In `rank_key`, a record that is recent (within `recency_years`) AND high evidence-tier (`pub_tier <= 1`: guideline/SR/meta/RCT/trial) is promoted up to `recency_boost` relevance buckets (floored at 0). `recency_boost=0` is a no-op (byte-identical ordering to today).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_literature_retriever.py`:

```python
def _recency_client():
    # p0..p4 are older (2010) narrative reviews in relevance bucket 0 (ranks 0-4);
    # p5 is a recent (2024) RCT in relevance bucket 1 (rank 5). Mechanism B promotes
    # the recent high-tier paper one bucket so it competes with bucket 0.
    class C:
        async def search(self, query, *, max_results=40, filter_type=None):
            if filter_type == "systematic_review":
                return ([], 0)
            return (["p0", "p1", "p2", "p3", "p4", "p5"], 6)

        async def summaries(self, pmids):
            rows = []
            for p in pmids:
                if p == "p5":
                    rows.append({"pmid": p, "title": f"t {p}", "source": "J",
                                 "pubdate": "2024", "pub_types": ["Randomized Controlled Trial"],
                                 "doi": "", "url": p, "authors": ""})
                else:
                    rows.append({"pmid": p, "title": f"t {p}", "source": "J",
                                 "pubdate": "2010", "pub_types": ["Review"],
                                 "doi": "", "url": p, "authors": ""})
            return rows

        async def structured_abstracts(self, pmids):
            return {p: {"RESULTS": "r"} for p in pmids}

        async def abstracts(self, pmids):
            return {p: "a" for p in pmids}
    return C()


def test_recency_boost_promotes_recent_high_tier():
    recs = asyncio.run(LiteratureRetriever(_recency_client(), k=8, recency_years=7,
                                           recency_boost=1).retrieve("q", current_year=2024))
    assert recs[0].pmid == "p5"  # promoted across the bucket boundary to the front


def test_recency_boost_zero_is_noop():
    recs = asyncio.run(LiteratureRetriever(_recency_client(), k=8, recency_years=7,
                                           recency_boost=0).retrieve("q", current_year=2024))
    order = [r.pmid for r in recs]
    assert order.index("p0") < order.index("p5")  # relevance bucket order preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_literature_retriever.py::test_recency_boost_promotes_recent_high_tier tests/test_literature_retriever.py::test_recency_boost_zero_is_noop -v`
Expected: FAIL — `test_recency_boost_promotes_recent_high_tier` fails (`recs[0].pmid == 'p0'`) and `__init__` rejects `recency_boost` (`TypeError`).

- [ ] **Step 3: Write minimal implementation**

In `neuro_caseboard/literature/retriever.py`, update `__init__`:

```python
    def __init__(self, client, *, k: int = 8, recency_years: int = 7, recency_boost: int = 0):
        self._client = client
        self._k = k
        self._recency_years = recency_years
        self._recency_boost = recency_boost
        # Set by retrieve(): explains thin coverage (BACKLOG P2 #7) for the caller to surface.
        self.last_coverage_note = ""
```

Replace the `rank_key` closure body (lines ~166-171) with:

```python
        def rank_key(r: LiteratureRecord):
            # Bucket by relevance, then prefer evidence quality + recency WITHIN a bucket:
            # relevance gates selection; tier/recency only reorder similarly-relevant papers.
            bucket = rank_of.get(r.pmid, len(pmids)) // _RELEVANCE_BUCKET
            tier = pub_tier(r.pub_types)
            recent = 0 if (r.year and current_year - r.year <= self._recency_years) else 1
            # Mechanism B: a recent, high-evidence paper (guideline/SR/meta/RCT) may be promoted
            # up to recency_boost buckets so a landmark recent trial just below the relevance
            # cutoff is not buried. Conservative; recency_boost=0 is a no-op (today's behavior).
            if self._recency_boost and recent == 0 and tier <= 1:
                bucket = max(0, bucket - self._recency_boost)
            return (bucket, tier, recent, -(r.year or 0))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_literature_retriever.py -v`
Expected: PASS (all tests, including the existing `test_retrieve_merges_axes_ranks_and_caps` and `test_relevance_gates_high_tier_low_relevance` — they pass `recency_boost=0` by default, so ordering is unchanged).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/retriever.py tests/test_literature_retriever.py
git commit -m "feat(lit): recency tie-breaker (mechanism B) promoting recent high-tier papers"
```

---

### Task 3: Deterministic precision gate

**Files:**
- Create: `neuro_caseboard/literature/precision.py`
- Test: `tests/test_literature_precision.py`

**Interfaces:**
- Consumes: `LiteratureRecord` (has `.title`, `.abstract`), `build_query_terms` (Lane B tokenizer).
- Produces: `gate_records(records, query, *, min_overlap=1, rank_ceiling=None) -> GateResult` where `GateResult` has `.records: list` and `.note: str`. Keeps a record when `title + abstract` shares `>= min_overlap` concept tokens (from `build_query_terms(query, max_terms=20)`) with the query; drops the rest. Empty input → empty result, no note. Empty query-concepts → pass-through (no gate). Empty-after-gate → keep the single first (most-relevant) record with a caution note.

- [ ] **Step 1: Write the failing test**

Create `tests/test_literature_precision.py`:

```python
from neuro_caseboard.literature.precision import gate_records, GateResult
from neuro_caseboard.literature.retriever import LiteratureRecord


def _rec(pmid, title, abstract):
    return LiteratureRecord(pmid=pmid, title=title, journal="J", year=2024, doi="",
                            url="u", abstract=abstract, sections={}, pub_types=["Review"])


def test_drops_offtopic_keeps_ontopic():
    on = _rec("1", "Middle meningeal artery embolization for subdural hematoma", "MMA outcomes")
    off = _rec("2", "Lumbar fusion hardware failure", "spine screws")
    res = gate_records([on, off], "subdural hematoma MMA embolization")
    assert isinstance(res, GateResult)
    assert [r.pmid for r in res.records] == ["1"]
    assert res.note == ""


def test_empty_input_returns_empty():
    res = gate_records([], "anything")
    assert res.records == [] and res.note == ""


def test_empty_concepts_passes_through():
    # build_query_terms drops <3-char tokens and stopwords; "of to" yields no concepts.
    a, b = _rec("1", "x", "y"), _rec("2", "p", "q")
    res = gate_records([a, b], "of to")
    assert [r.pmid for r in res.records] == ["1", "2"]
    assert res.note == ""


def test_all_offtopic_falls_back_to_top1_with_note():
    a = _rec("1", "Lumbar fusion", "spine")
    b = _rec("2", "Cervical plate", "spine")
    res = gate_records([a, b], "glioblastoma temozolomide")
    assert [r.pmid for r in res.records] == ["1"]  # single most-relevant kept
    assert "caution" in res.note.lower()


def test_min_overlap_threshold():
    # Needs >=2 shared concepts to survive at min_overlap=2.
    one = _rec("1", "subdural hematoma", "only one concept present")
    two = _rec("2", "subdural hematoma MMA embolization", "two-plus concepts")
    res = gate_records([one, two], "subdural hematoma MMA embolization", min_overlap=2)
    assert [r.pmid for r in res.records] == ["2"]


def test_rank_ceiling_caps_pool():
    recs = [_rec(str(i), "subdural hematoma MMA", "embolization") for i in range(5)]
    res = gate_records(recs, "subdural hematoma MMA embolization", rank_ceiling=3)
    assert [r.pmid for r in res.records] == ["0", "1", "2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_literature_precision.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_caseboard.literature.precision'`.

- [ ] **Step 3: Write minimal implementation**

Create `neuro_caseboard/literature/precision.py`:

```python
"""Deterministic topical-relevance gate applied to ranked literature BEFORE woven synthesis.

Weaving literature inline makes off-topic "citation noise" more damaging than it is in a
siloed block, so this gate drops records that don't share the query's core concepts. Pure:
no network, no LLM. Concepts come from the same tokenizer the retriever uses for fallback
queries (build_query_terms), so the gate sees the same vocabulary the search did."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateResult:
    records: list = field(default_factory=list)
    note: str = ""


def _concepts(query: str) -> set:
    from neuro_caseboard.literature.retriever import build_query_terms
    return set(build_query_terms(query, max_terms=20).split())


def gate_records(records: list, query: str, *, min_overlap: int = 1,
                 rank_ceiling: int | None = None) -> GateResult:
    """Keep records whose title+abstract shares >= min_overlap concept tokens with the query.

    Empty input -> empty result. No extractable concepts -> pass-through (never gate to empty
    on a degenerate query). Empty after gating -> keep the single most-relevant (first) record
    with a caution note, mirroring standardize_records' thin-coverage fallback."""
    if not records:
        return GateResult(records=[], note="")
    pool = records if rank_ceiling is None else records[:rank_ceiling]
    concepts = _concepts(query)
    if not concepts:
        return GateResult(records=list(pool), note="")
    kept = []
    for r in pool:
        hay = f"{r.title} {r.abstract}".lower()
        if sum(1 for c in concepts if c in hay) >= min_overlap:
            kept.append(r)
    if kept:
        return GateResult(records=kept, note="")
    return GateResult(records=list(pool[:1]),
                      note="No literature passed the topical relevance gate; showing the "
                           "single most relevant article — interpret with caution.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_literature_precision.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/precision.py tests/test_literature_precision.py
git commit -m "feat(lit): deterministic precision gate for woven literature"
```

---

### Task 4: Engine retrieve-only seam

**Files:**
- Modify: `neuro_core/query.py:27-48` (add dataclass), `:193-237` (add method + module fn)
- Test: `tests/neuro_core/test_retrieve_for_synthesis.py`

**Interfaces:**
- Consumes: existing `Engine._plan_query` (returns `Clarification | _Resolved`), `Engine._collect_figures`.
- Produces:
  - `RetrievalBundle(question: str, hits: list, figures: list, images: list, variant)` dataclass.
  - `Engine.retrieve_for_synthesis(question) -> Clarification | RetrievalBundle` — runs `_plan_query`; on `Clarification` returns it; else collects figures/images and returns a bundle with the (possibly variant-resolved) question + variant.
  - `plan_retrieval(question, config=None, force=False) -> Clarification | RetrievalBundle` — module-level; runs the same GPU guard as `query()` then delegates to the cached engine.

- [ ] **Step 1: Write the failing test**

Create `tests/neuro_core/test_retrieve_for_synthesis.py`:

```python
import neuro_core.query as q
from neuro_core.query import Engine, RetrievalBundle, Clarification
from neuro_core.query_analyze import VariantRewrite, Gate, QueryAnalysis
from neuro_core.index import Hit

# Reuse the fakes from the sibling engine test module.
from tests.neuro_core.test_query import (
    FakeConfig, FakeEmbedder, FakeIndex, FakeReranker, FakeSynthClient, capturing_synth,
)


def _engine(index, gate_fn=None, analyze_fn=None):
    return Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                  synth_client=FakeSynthClient(), synth_fn=capturing_synth,
                  gate_fn=gate_fn or (lambda question, hits: Gate(tripped=False)),
                  analyze_fn=analyze_fn or (lambda q, h, sc: QueryAnalysis(ambiguous=False)))


def test_retrieve_for_synthesis_returns_bundle_no_synth():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]
    sc = FakeSynthClient()
    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=sc, synth_fn=capturing_synth,
                 gate_fn=lambda question, h: Gate(tripped=False))
    bundle = eng.retrieve_for_synthesis("normal icp?")
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.question == "normal icp?"
    assert [h.page for h in bundle.hits] == [1, 2]
    assert bundle.figures == [] and bundle.images == []
    assert bundle.variant is None
    assert sc.captured == {}  # synthesis NOT called


def test_retrieve_for_synthesis_short_circuits_clarification():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    vr1 = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    vr2 = VariantRewrite("bifrontal (Kjellberg) decompression", "bifrontal rewrite")
    analyze = lambda qq, h, sc: QueryAnalysis(ambiguous=True, axis="x",
                                              variants=[vr1, vr2], chosen=vr1, confidence=0.2)
    eng = _engine(FakeIndex(hits), gate_fn=lambda question, h: Gate(tripped=True, axis="x"),
                  analyze_fn=analyze)
    out = eng.retrieve_for_synthesis("decompressive craniectomy steps?")
    assert isinstance(out, Clarification)


def test_retrieve_for_synthesis_carries_resolved_variant():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    analyze = lambda qq, h, sc: QueryAnalysis(
        ambiguous=True, axis="x",
        variants=[vr, VariantRewrite("bifrontal (Kjellberg) decompression", "b rewrite")],
        chosen=vr, confidence=0.9)
    index = FakeIndex(hits)
    eng = _engine(index, gate_fn=lambda question, h: Gate(tripped=True, axis="x"),
                  analyze_fn=analyze)
    bundle = eng.retrieve_for_synthesis("decompressive craniectomy steps?")
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.question == "uni rewrite"
    assert bundle.variant is vr
    assert index.called_with[0] == "uni rewrite"  # figures collected on the resolved query


def test_plan_retrieval_runs_guard_for_local(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "local"
        gpu_guard = True

    class _E:
        def retrieve_for_synthesis(self, question):
            return f"BUNDLE:{question}"

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("force", force))
    monkeypatch.setattr(q, "get_engine", lambda config: _E())
    out = q.plan_retrieval("hi", config=Cfg(), force=True)
    assert out == "BUNDLE:hi"
    assert calls["force"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/neuro_core/test_retrieve_for_synthesis.py -v`
Expected: FAIL — `ImportError: cannot import name 'RetrievalBundle'`.

- [ ] **Step 3: Write minimal implementation**

In `neuro_core/query.py`, add the dataclass after `QueryResult` (near line 32):

```python
@dataclass
class RetrievalBundle:
    """Retrieval-only output for the woven Ask path: the (possibly variant-resolved)
    question plus retrieved passages and collected figures/images, WITHOUT synthesis.
    Synthesis happens in the neuro_caseboard integration layer so neuro_core stays
    literature-agnostic."""
    question: str
    hits: list = field(default_factory=list)
    figures: list = field(default_factory=list)
    images: list = field(default_factory=list)
    variant: VariantRewrite | None = None
```

Add the method to `Engine` (after `select_figures`, before `_answer`):

```python
    def retrieve_for_synthesis(self, question):
        """Retrieve passages + figures without synthesizing (for the woven Ask path).
        Returns a Clarification (ambiguous, no answer) or a RetrievalBundle."""
        plan = self._plan_query(question)
        if isinstance(plan, Clarification):
            return plan
        figures, images = self._collect_figures(plan.question, plan.top)
        return RetrievalBundle(question=plan.question, hits=plan.top, figures=figures,
                               images=images, variant=plan.variant)
```

Add the module-level function after `query()` (end of file):

```python
def plan_retrieval(question, config=None, force=False):
    config = config or load_config()
    if config.synth_provider == "local" and config.gpu_guard:
        ensure_gpu_ready(config, force=force)
    return get_engine(config).retrieve_for_synthesis(question)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/neuro_core/test_retrieve_for_synthesis.py tests/neuro_core/test_query.py -v`
Expected: PASS (new file + existing engine tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/query.py tests/neuro_core/test_retrieve_for_synthesis.py
git commit -m "feat(core): retrieve-only seam (RetrievalBundle + plan_retrieval) for woven Ask"
```

---

### Task 5: Woven synthesizer

**Files:**
- Create: `neuro_caseboard/woven_synth.py`
- Test: `tests/test_woven_synth.py`

**Interfaces:**
- Consumes: `neuro_core.synthesize` helpers `_format_passages`, `_appended_figures`, `_format_appended`, `_figure_note`, `Citation`, `REFUSAL`; `neuro_caseboard.literature.synth._format_studies`; `LiteratureRecord` (Task 2).
- Produces:
  - `WovenSynthesis(answer: str, citations: list, records: list)` — `citations` are `neuro_core` `Citation` (`[n]`, textbook + appended figures); `records` echoes the literature records used (caller builds `[L#]`).
  - `WOVEN_SYSTEM` prompt string.
  - `synthesize_woven(question, hits, figures, images, records, synth_client, *, variant_directive=None) -> WovenSynthesis` — single `synth_client.generate` call over both evidence blocks. No retry/refusal/variant handling here (the orchestrator in Task 6 owns those, mirroring `Engine._answer`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_woven_synth.py`:

```python
from neuro_caseboard.woven_synth import synthesize_woven, WovenSynthesis, WOVEN_SYSTEM
from neuro_caseboard.literature.retriever import LiteratureRecord
from neuro_core.index import Hit


class _Spy:
    def __init__(self, reply="Woven answer [1] and recent trial [L1]."):
        self.reply = reply
        self.system = None
        self.user = None
        self.images = None

    def generate(self, system, user, images):
        self.system, self.user, self.images = system, user, images
        return self.reply


def _hit(n):
    return Hit(id=str(n), book="Greenberg", chapter="Ch", page=n, text=f"passage {n}")


def _rec(pmid="111"):
    return LiteratureRecord(pmid=pmid, title="DISTAL trial", journal="NEJM", year=2024,
                            doi="10/x", url="u", abstract="distal occlusion thrombectomy",
                            sections={}, pub_types=["Randomized Controlled Trial"])


def test_woven_includes_both_blocks_and_builds_citations():
    spy = _Spy()
    out = synthesize_woven("q", [_hit(1), _hit(2)], [], [], [_rec("111")], spy)
    assert isinstance(out, WovenSynthesis)
    assert out.answer == "Woven answer [1] and recent trial [L1]."
    assert "Textbook passages:" in spy.user
    assert "[1] Greenberg, Ch, p.1" in spy.user
    assert "Contemporary studies:" in spy.user
    assert "[L1] DISTAL trial" in spy.user
    assert [c.n for c in out.citations] == [1, 2]
    assert [r.pmid for r in out.records] == ["111"]
    assert spy.system is WOVEN_SYSTEM


def test_woven_without_records_omits_studies_block():
    spy = _Spy(reply="Textbook only [1].")
    out = synthesize_woven("q", [_hit(1)], [], [], [], spy)
    assert "Contemporary studies:" not in spy.user
    assert out.records == []
    assert [c.n for c in out.citations] == [1]


def test_woven_passes_images_and_variant_directive():
    spy = _Spy()
    synthesize_woven("q", [_hit(1)], [], [b"PNG"], [_rec()], spy,
                     variant_directive="Answer for the variant 'X' ONLY.")
    assert spy.images == [b"PNG"]
    assert "Answer for the variant 'X' ONLY." in spy.user


def test_woven_prompt_contract_strings():
    # The prompt must keep namespaces distinct, define the textbook-silent flag, and
    # emit the shared REFUSAL verbatim so is_refusal() matches downstream.
    from neuro_core.synthesize import REFUSAL
    assert "[L#]" in WOVEN_SYSTEM and "[n]" in WOVEN_SYSTEM
    assert REFUSAL in WOVEN_SYSTEM
    assert "textbook corpus did not cover" in WOVEN_SYSTEM.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_woven_synth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_caseboard.woven_synth'`.

- [ ] **Step 3: Write minimal implementation**

Create `neuro_caseboard/woven_synth.py`:

```python
"""Woven synthesis: ONE answer from textbook passages ([n]) and PubMed studies ([L#]).

Retrieval stays two separate lanes (neuro_core textbook, neuro_caseboard.literature PubMed);
only synthesis merges here. The two citation namespaces are kept distinct inline. This module
lives in neuro_caseboard so neuro_core stays literature-agnostic; it reuses neuro_core's passage/
figure formatters and the literature study formatter rather than duplicating them.

Retry/empty-guard/refusal/variant-prepend are intentionally NOT here — the orchestrator
(qa._answer_question_woven) owns them, mirroring Engine._answer for the non-woven path."""
from __future__ import annotations

from dataclasses import dataclass, field

from neuro_core.synthesize import REFUSAL

WOVEN_SYSTEM = (
    "You are a neurosurgical reference assistant. Write ONE integrated answer using two "
    "evidence sources: numbered textbook passages (cited [n], e.g. [2]) and numbered "
    "contemporary studies (cited [L#], e.g. [L3]). Rules:\n"
    "- Cite the bracketed source number for every clinical claim. Keep the two citation "
    "styles DISTINCT: textbook claims use [n]; literature claims use [L#]. Never renumber "
    "or merge them.\n"
    "- Weave the literature INTO the textbook answer where it updates, extends, confirms, "
    "or contradicts the textbook — do not append it as a separate section or restate it "
    "twice.\n"
    "- Some textbook sources include an attached page image (a figure/plate). When an image "
    "is attached for a source, you may describe what the figure shows and must still cite "
    "that source number. Do not describe images that are not attached.\n"
    "- If the textbook passages do NOT cover the question but the studies do, answer from "
    "the studies ([L#]) and add one sentence: \"The textbook corpus did not cover this; "
    "this answer rests on contemporary literature.\"\n"
    f"- If NEITHER the passages nor the studies contain the answer, say \"{REFUSAL}\"\n"
    "- If sources disagree, state the disagreement explicitly and attribute each view to "
    "its source.\n"
    "- Be concise and clinically precise. This is decision-support, not a substitute for "
    "clinical judgment."
)


@dataclass
class WovenSynthesis:
    answer: str
    citations: list = field(default_factory=list)   # neuro_core Citation, [n]
    records: list = field(default_factory=list)      # literature records used, for [L#]


def synthesize_woven(question, hits, figures, images, records, synth_client,
                     *, variant_directive=None) -> WovenSynthesis:
    from neuro_core.synthesize import (
        _format_passages, _appended_figures, _format_appended, _figure_note, Citation)
    from neuro_caseboard.literature.synth import _format_studies

    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nTextbook passages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if records:
        user += f"\n\nContemporary studies:\n{_format_studies(records)}"
    if variant_directive:
        user += "\n\n" + variant_directive

    answer = synth_client.generate(WOVEN_SYSTEM, user, images)

    citations = [Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
                 for i, h in enumerate(hits, 1)]
    for f in appended:
        citations.append(Citation(n=f.source_n, book=f.book, chapter=f.chapter or "",
                                  page=f.page))
    return WovenSynthesis(answer=answer, citations=citations, records=list(records))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_woven_synth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/woven_synth.py tests/test_woven_synth.py
git commit -m "feat(qa): woven synthesizer over textbook [n] + literature [L#]"
```

---

### Task 6: Woven orchestration in qa.py

**Files:**
- Modify: `neuro_caseboard/qa.py` (refactor `build_literature_section`; add `retrieve_records`, `_retrieve_literature_for_weave`, `_answer_question_woven`; branch in `answer_question`)
- Test: `tests/test_woven_qa.py`, and one routing test added to `tests/test_qa.py`

**Interfaces:**
- Consumes: `plan_retrieval`, `RetrievalBundle`, `Clarification`, `_variant_directive` (Task 4); `REFUSAL`, `is_refusal` (`neuro_core.synthesize`); `synthesize_woven` (Task 5); `gate_records` (Task 3); `LiteratureConfig.weave/precision_gate/precision_min_overlap` (Task 1).
- Produces:
  - `retrieve_records(question, *, lit_config, client=None, synth_client, cache=None) -> (records, search_query)` — Lane B retrieval only (cache + rewrite + retry + recency-boosted ranking), no synthesis. `search_query` is the focused query actually used (term fallback on cache hit).
  - `_retrieve_literature_for_weave(question, *, lit_config, synth_client) -> list` — calls `retrieve_records`, applies the precision gate, returns records (failure-safe → `[]`).
  - `_answer_question_woven(question, *, config=None, force=False, lit_config, synth_client=None, plan_a=None, retrieve_b=None) -> QAResult | Clarification`.
  - `answer_question` routes to `_answer_question_woven` when `lit_config.weave` is on and no lanes were injected.
  - `QAResult` shape unchanged. In woven mode, `literature` is a `LiteratureSection(narrative="", citations=[L#])` (narrative empty — the prose is woven into `answer`), or `None` when no records survived.

- [ ] **Step 1: Write the failing test**

Create `tests/test_woven_qa.py`:

```python
from types import SimpleNamespace

from neuro_caseboard.qa import _answer_question_woven, QAResult
from neuro_caseboard.literature.config import LiteratureConfig
from neuro_caseboard.literature.retriever import LiteratureRecord
from neuro_core.query import RetrievalBundle, Clarification
from neuro_core.query_analyze import VariantRewrite
from neuro_core.index import Hit


def _cfg():
    return LiteratureConfig(enabled=True, recency_years=7, k=5, cache_ttl_days=14,
                            ncbi_api_key="", cache_dir="/tmp/x", weave=True,
                            recency_boost=0, precision_gate=True, precision_min_overlap=1)


def _bundle(question="q", variant=None):
    return RetrievalBundle(question=question,
                           hits=[Hit(id="a", book="B", chapter="C", page=1, text="t1")],
                           figures=[], images=[], variant=variant)


def _rec(pmid="111"):
    return LiteratureRecord(pmid=pmid, title="T", journal="J", year=2024, doi="d", url="u",
                            abstract="a", sections={}, pub_types=["Review"])


class _Synth:
    def __init__(self, reply):
        self.reply = reply

    def generate(self, system, user, images):
        return self.reply


def test_woven_happy_path_one_block_two_namespaces():
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Answer [1] with trial [L1]."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec("111")])
    assert isinstance(out, QAResult)
    assert out.answer == "Answer [1] with trial [L1]."
    assert [c.n for c in out.citations] == [1]
    assert out.literature is not None
    assert out.literature.narrative == ""             # prose is woven into `answer`
    assert [c.n for c in out.literature.citations] == [1]
    assert out.literature.citations[0].pmid == "111"


def test_woven_no_records_literature_is_none():
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Textbook only [1]."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [])
    assert out.answer == "Textbook only [1]."
    assert out.literature is None


def test_woven_clarification_short_circuits():
    clar = Clarification(question="q", variants=[VariantRewrite("A", "a"),
                                                 VariantRewrite("B", "b")])
    out = _answer_question_woven("q", lit_config=_cfg(), synth_client=_Synth("x"),
                                 plan_a=lambda: clar, retrieve_b=lambda: [_rec()])
    assert out is clar


def test_woven_refusal_drops_citations_and_literature():
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Not found in the provided sources."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec()])
    assert out.answer == "Not found in the provided sources."
    assert out.citations == []
    assert out.figures == []
    assert out.literature is None


def test_woven_empty_answer_retries_then_refuses():
    calls = {"n": 0}

    class _EmptySynth:
        def generate(self, system, user, images):
            calls["n"] += 1
            return "   "  # always empty/whitespace

    out = _answer_question_woven("q", lit_config=_cfg(), synth_client=_EmptySynth(),
                                 plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec()])
    assert out.answer == "Not found in the provided sources."
    assert calls["n"] == 2  # one retry, then degrade


def test_woven_variant_prepends_assuming_line():
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Body [1]."),
        plan_a=lambda: _bundle(question="uni rewrite", variant=vr),
        retrieve_b=lambda: [])
    assert out.answer.startswith("**Assuming unilateral FTP hemicraniectomy")
    assert "Body [1]." in out.answer


def test_woven_lane_b_failure_is_additive():
    def boom():
        raise RuntimeError("pubmed down")

    out = _answer_question_woven("q", lit_config=_cfg(), synth_client=_Synth("Textbook [1]."),
                                 plan_a=lambda: _bundle(), retrieve_b=boom)
    assert out.answer == "Textbook [1]."
    assert out.literature is None  # literature failure never blocks the answer
```

Add to `tests/test_qa.py`:

```python
def test_answer_question_routes_to_woven_when_flag_on(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    import neuro_caseboard.qa as qa
    monkeypatch.setattr(qa, "_answer_question_woven", lambda *a, **k: "WOVEN")
    assert qa.answer_question("q") == "WOVEN"


def test_answer_question_separate_path_when_flag_off(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.delenv("LITERATURE_WEAVE", raising=False)
    out = answer_question("q", lane_a=_query_result, lane_b=lambda: None)
    assert isinstance(out, QAResult)
    assert out.answer == "Textbook answer [1]."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_woven_qa.py tests/test_qa.py::test_answer_question_routes_to_woven_when_flag_on -v`
Expected: FAIL — `ImportError: cannot import name '_answer_question_woven'`.

- [ ] **Step 3: Write minimal implementation**

In `neuro_caseboard/qa.py`, **refactor** `build_literature_section` to use a new `retrieve_records`. Replace the body of `build_literature_section` (lines 41-100) with:

```python
def retrieve_records(question, *, lit_config, client=None, synth_client, cache=None):
    """Lane B retrieval only (no synthesis). Returns (records, search_query).

    records is a list (possibly empty); search_query is the focused query actually used
    (the LLM rewrite on a cache miss, else the deterministic term). Cache key and rewrite
    ordering are preserved from the original build_literature_section so behavior is
    unchanged: rewrite is NOT called on a cache hit."""
    from neuro_caseboard.literature.retriever import (
        LiteratureRetriever, build_query_terms, rewrite_pubmed_query)

    if cache is None:
        from neuro_caseboard.literature.cache import LiteratureCache
        cache = LiteratureCache(lit_config.cache_dir, ttl_days=lit_config.cache_ttl_days)
    term = build_query_terms(question)
    search_query = term
    key = f"{term}|{lit_config.k}|{lit_config.recency_years}"
    records = cache.get(key)
    if records is None:
        owns_client = client is None
        if client is None:
            from neuro_caseboard.literature.pubmed_client import PubMedClient
            client = PubMedClient(api_key=lit_config.ncbi_api_key)
        retriever = LiteratureRetriever(client, k=lit_config.k,
                                        recency_years=lit_config.recency_years,
                                        recency_boost=lit_config.recency_boost)
        search_query = rewrite_pubmed_query(question, synth_client) or term

        async def _retrieve():
            try:
                recs = await retriever.retrieve(question, query=search_query)
                if not recs and search_query != term:
                    recs = await retriever.retrieve(question, query=term)
                return recs
            finally:
                if owns_client:
                    await client.aclose()

        records = asyncio.run(_retrieve())
        cache.set(key, records)  # empty results are cached (records == []) to avoid re-hitting NCBI
    return records, search_query


def build_literature_section(question, *, config=None, lit_config=None,
                             client=None, synth_client=None, cache=None):
    """Run Lane B end to end (separate-block mode). Returns a LiteratureSection or None."""
    from neuro_caseboard.literature.config import load_literature_config
    from neuro_caseboard.literature.synth import synthesize_literature

    lit_config = lit_config or load_literature_config()
    if not lit_config.enabled:
        return None
    try:
        if synth_client is None:
            from neuro_core.config import load_config
            from neuro_core.synth_clients import make_synth_client
            synth_client = make_synth_client(config or load_config())
        records, _ = retrieve_records(question, lit_config=lit_config, client=client,
                                      synth_client=synth_client, cache=cache)
        if not records:
            return None
        syn = synthesize_literature(question, records, synth_client)
        if syn is None:
            return None
        cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                    year=r.year, doi=r.doi, url=r.url)
                 for i, r in enumerate(syn.records, 1)]
        return LiteratureSection(narrative=syn.narrative, citations=cites)
    except Exception:
        _log.debug("literature lane failed", exc_info=True)
        return None
```

Then add the woven Lane B helper and orchestrator (after `build_literature_section`, before `answer_question`):

```python
def _retrieve_literature_for_weave(question, *, lit_config, synth_client):
    """Woven Lane B: retrieve + precision-gate. Returns list[LiteratureRecord] (failure-safe → [])."""
    if not lit_config.enabled:
        return []
    try:
        records, search_query = retrieve_records(question, lit_config=lit_config,
                                                 synth_client=synth_client)
        if not records:
            return []
        if lit_config.precision_gate:
            from neuro_caseboard.literature.precision import gate_records
            records = gate_records(records, search_query,
                                   min_overlap=lit_config.precision_min_overlap).records
        return records
    except Exception:
        _log.debug("woven literature retrieval failed", exc_info=True)
        return []


def _answer_question_woven(question, *, config=None, force=False, lit_config=None,
                           synth_client=None, plan_a=None, retrieve_b=None):
    """One woven answer from textbook ([n]) + literature ([L#]). Lane A errors propagate;
    Lane B failures degrade to a textbook-only answer. Mirrors Engine._answer's empty-guard,
    refusal handling, and variant prepend (the woven path bypasses Engine._answer)."""
    from neuro_core.query import Clarification, plan_retrieval, _variant_directive
    from neuro_core.synthesize import REFUSAL, is_refusal
    from neuro_caseboard.woven_synth import synthesize_woven

    if synth_client is None:
        from neuro_core.config import load_config
        from neuro_core.synth_clients import make_synth_client
        synth_client = make_synth_client(config or load_config())
    if plan_a is None:
        def plan_a():
            return plan_retrieval(question, config=config, force=force)
    if retrieve_b is None:
        def retrieve_b():
            return _retrieve_literature_for_weave(question, lit_config=lit_config,
                                                  synth_client=synth_client)

    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(plan_a)
        fb = ex.submit(retrieve_b)
        plan = fa.result()  # Lane A errors propagate (e.g. GpuNotReadyError)
        if isinstance(plan, Clarification):
            return plan
        try:
            records = fb.result()
        except Exception:
            _log.debug("woven literature lane raised in executor", exc_info=True)
            records = []

    directive = _variant_directive(plan.variant.label) if plan.variant else None

    def _synth():
        return synthesize_woven(plan.question, plan.hits, plan.figures, plan.images,
                                records, synth_client, variant_directive=directive)

    syn = _synth()
    # Empty-answer guard (parity with Engine._answer / TKT-C5): a transient empty/whitespace
    # result is not a refusal; retry once, then degrade to the honest REFUSAL so the caller
    # never receives a blank, not-gradable answer.
    if not (syn.answer or "").strip():
        syn = _synth()
        if not (syn.answer or "").strip():
            return QAResult(answer=REFUSAL, citations=[], figures=[], literature=None)
    if is_refusal(syn.answer):
        # Abstention: figures/citations/literature collected from retrieval are spurious.
        return QAResult(answer=syn.answer, citations=[], figures=[], literature=None)

    answer = syn.answer
    if plan.variant is not None:
        answer = (f"**Assuming {plan.variant.label} (most consistent with retrieved "
                  "sources).**\n\n" + answer)

    lit = None
    if syn.records:
        cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                    year=r.year, doi=r.doi, url=r.url)
                 for i, r in enumerate(syn.records, 1)]
        lit = LiteratureSection(narrative="", citations=cites)
    return QAResult(answer=answer, citations=syn.citations, figures=plan.figures,
                    literature=lit)
```

Finally, branch in `answer_question` — insert at the very top of the function body (before the `if lane_a is None` block):

```python
    # Woven mode (flag-gated): one integrated answer. Only when no lanes were injected, so
    # the separate-path tests (which inject lane_a/lane_b) are unaffected.
    if lane_a is None and lane_b is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
        if lit_config.weave:
            return _answer_question_woven(question, config=config, force=force,
                                          lit_config=lit_config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_woven_qa.py tests/test_qa.py -v`
Expected: PASS (new woven tests + existing qa tests — `build_literature_section` behavior preserved).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/qa.py tests/test_woven_qa.py tests/test_qa.py
git commit -m "feat(qa): woven Ask orchestration (retrieve-only A + gated B + one synthesis)"
```

---

### Task 7: CLI renders woven output

**Files:**
- Modify: `neuro_caseboard/cli.py:31-42`
- Test: `tests/test_cli_literature.py`

**Interfaces:**
- Consumes: `QAResult` with `literature` possibly having `narrative == ""` and non-empty `citations` (woven mode).
- Produces: `_run_ask` prints the `[L#]` reference list whenever `literature.citations` exist (narrative optional). The "Contemporary Literature:" narrative line is printed only when `narrative` is non-empty (separate mode), so flag-off output is unchanged.

- [ ] **Step 1: Write the failing test**

Inspect `tests/test_cli_literature.py` for the existing capture helper and follow its pattern. Add:

```python
def test_cli_renders_woven_literature_refs_without_narrative(capsys, monkeypatch):
    from types import SimpleNamespace
    import neuro_caseboard.cli as cli
    woven = SimpleNamespace(
        answer="Woven answer [1] with recent trial [L1].",
        citations=[SimpleNamespace(n=1, book="Greenberg", chapter="Ch", page=5)],
        figures=[],
        literature=SimpleNamespace(narrative="", citations=[
            SimpleNamespace(n=1, title="DISTAL trial", journal="NEJM", year=2024,
                            doi="10/x", url="u")]))
    monkeypatch.setattr(cli, "_answer_question", lambda q, force=False: woven)
    rc = cli.main(["ask", "distal occlusion?"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Woven answer [1] with recent trial [L1]." in out
    assert "Contemporary Literature:" in out
    assert "[L1] DISTAL trial" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_literature.py::test_cli_renders_woven_literature_refs_without_narrative -v`
Expected: FAIL — the `[L1]` line is not printed because the current guard requires `lit.narrative`.

- [ ] **Step 3: Write minimal implementation**

In `neuro_caseboard/cli.py`, replace the literature block in `_run_ask` (lines 36-42):

```python
    lit = getattr(result, "literature", None)
    if lit and lit.citations:
        print("\nContemporary Literature:")
        if lit.narrative:  # separate mode carries a standalone narrative; woven mode does not
            print(lit.narrative)
        for c in lit.citations:
            link = f"https://doi.org/{c.doi}" if c.doi else c.url
            print(f"  [L{c.n}] {c.title} — {c.journal} {c.year or ''} · {link}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_literature.py -v`
Expected: PASS (new test + existing separate-mode CLI tests unchanged — they carry a narrative).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cli.py tests/test_cli_literature.py
git commit -m "feat(cli): render woven [L#] reference list (narrative optional)"
```

---

### Task 8: PDF/HTML briefing renders woven output

**Files:**
- Modify: `neuro_caseboard/briefing_pdf.py:94-116` (HTML), `:252-267` (fpdf fallback)
- Test: `tests/test_briefing_literature.py`

**Interfaces:**
- Consumes: same woven `QAResult` shape as Task 7.
- Produces: `_literature_html` renders the `[L#]` reference list when `cites` exist (narrative optional); the narrative `<div class="answer">` is emitted only when `narrative` is non-empty. The fpdf fallback mirrors this (reference list when citations present; narrative lines only when present). Flag-off output unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_briefing_literature.py` (follow the file's existing `_g`/result-shape pattern):

```python
def test_literature_html_renders_refs_without_narrative():
    from types import SimpleNamespace
    from neuro_caseboard.briefing_pdf import _literature_html
    result = SimpleNamespace(literature=SimpleNamespace(
        narrative="",
        citations=[SimpleNamespace(n=1, title="DISTAL trial", journal="NEJM",
                                   year=2024, doi="10/x", url="u")]))
    html = _literature_html(result)
    assert "Contemporary Literature" in html
    assert "[L1]" in html and "DISTAL trial" in html


def test_literature_html_empty_when_no_citations():
    from types import SimpleNamespace
    from neuro_caseboard.briefing_pdf import _literature_html
    result = SimpleNamespace(literature=SimpleNamespace(narrative="", citations=[]))
    assert _literature_html(result) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_briefing_literature.py::test_literature_html_renders_refs_without_narrative -v`
Expected: FAIL — current `_literature_html` returns `""` when `narrative` is empty.

- [ ] **Step 3: Write minimal implementation**

In `neuro_caseboard/briefing_pdf.py`, replace the guard + narrative render in `_literature_html` (lines 99-116):

```python
    narrative = _g(lit, "narrative") or ""
    cites = _g(lit, "citations") or []
    if not cites:
        return ""
    rows = []
    for c in cites:
        doi = _g(c, "doi") or ""
        href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
        meta = ", ".join(p for p in (html.escape(_g(c, "journal") or ""),
                                     str(_g(c, "year") or "")) if p)
        link = f' · <a href="{html.escape(href)}">link</a>' if href else ""
        rows.append(f'<div class="src"><span class="ln">[L{_g(c, "n")}]</span> '
                    f'{html.escape(_g(c, "title") or "")} '
                    f'<span class="litmeta">— {meta}</span>{link}</div>')
    narrative_html = (f'<div class="answer">{_md_to_html(narrative)}</div>'
                      if narrative else "")
    return ('<div class="section"><div class="sec-h"><span class="k">LIT</span>'
            '<span class="t">Contemporary Literature</span><span class="ln"></span></div>'
            f'{narrative_html}'
            f'<div class="sources">{"".join(rows)}</div></div>')
```

In the fpdf fallback, replace the literature guard (line ~253):

```python
    lit = _g(result, "literature")
    if lit and (_g(lit, "citations") or []):
        pdf.ln(2); pdf.set_font(fam, "B", 13)
        pdf.multi_cell(0, 7, t("Contemporary Literature"), new_x="LMARGIN", new_y="NEXT")
        if _g(lit, "narrative"):
            pdf.set_font(fam, "", 10)
            for kind, text in _md_lines(_g(lit, "narrative")):
                pdf.multi_cell(0, 5, t(("- " + text) if kind == "li" else text),
                               new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for c in (_g(lit, "citations") or []):
            doi = _g(c, "doi") or ""
            href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
            meta = ", ".join(p for p in (_g(c, "journal") or "", str(_g(c, "year") or "")) if p)
            pdf.multi_cell(0, 4.6, t(f"[L{_g(c, 'n')}] {_g(c, 'title') or ''} -- {meta} {href}"),
                           new_x="LMARGIN", new_y="NEXT")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_briefing_literature.py -v`
Expected: PASS (new tests + existing separate-mode briefing tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_pdf.py tests/test_briefing_literature.py
git commit -m "feat(pdf): render woven [L#] reference list in HTML + fpdf fallback"
```

---

### Task 9: Streamlit renders woven output

**Files:**
- Modify: `app/streamlit_app.py:179-182`
- Test: `tests/test_streamlit_woven.py` (new; importorskip-guarded)

**Interfaces:**
- Consumes: same woven `QAResult` shape.
- Produces: the "Contemporary Literature" panel renders when `result.literature.citations` exist; the `citation_chips(narrative)` sub-block renders only when `narrative` is non-empty. Flag-off (separate mode) behavior unchanged.

**Note:** The Streamlit `render` path is tightly coupled to `st`/session state; rather than drive AppTest, this task asserts the rendering CONDITION via a tiny extracted helper so it is unit-testable without a running Streamlit. If `app/streamlit_app.py` cannot cleanly host a helper, fall back to an AppTest smoke test guarded by `pytest.importorskip("streamlit")`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_streamlit_woven.py`:

```python
import pytest
pytest.importorskip("streamlit")

from app.streamlit_app import _should_show_literature


def test_show_literature_when_citations_present_woven():
    from types import SimpleNamespace
    lit = SimpleNamespace(narrative="", citations=[SimpleNamespace(n=1)])
    assert _should_show_literature(lit) is True


def test_show_literature_separate_mode():
    from types import SimpleNamespace
    lit = SimpleNamespace(narrative="Recent RCTs [L1].", citations=[SimpleNamespace(n=1)])
    assert _should_show_literature(lit) is True


def test_hide_literature_when_no_citations():
    from types import SimpleNamespace
    assert _should_show_literature(None) is False
    assert _should_show_literature(SimpleNamespace(narrative="", citations=[])) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_streamlit_woven.py -v`
Expected: FAIL — `ImportError: cannot import name '_should_show_literature'` (or skip if streamlit absent; install via `.[web]` locally to run, otherwise rely on the logic being trivial).

- [ ] **Step 3: Write minimal implementation**

In `app/streamlit_app.py`, add a module-level helper (near the top, after imports):

```python
def _should_show_literature(lit) -> bool:
    """Woven mode carries [L#] citations with an empty narrative; separate mode carries both.
    Render the panel whenever citations exist (narrative is optional)."""
    return bool(lit and getattr(lit, "citations", None))
```

Replace the render block (lines 179-182):

```python
        if _should_show_literature(result.literature):
            sig.section("Contemporary Literature", "LIT")
            if result.literature.narrative:
                st.markdown(sig.citation_chips(result.literature.narrative),
                            unsafe_allow_html=True)
            sig.literature_panel(result.literature.citations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_streamlit_woven.py -v`
Expected: PASS if streamlit installed; SKIP otherwise (acceptable — CI `.[dev]` skips; logic is covered by the helper's triviality).

- [ ] **Step 5: Commit**

```bash
git add app/streamlit_app.py tests/test_streamlit_woven.py
git commit -m "feat(web): render woven [L#] panel in Streamlit (narrative optional)"
```

---

### Task 10: Scoped regression sweep + A/B validation handoff

**Files:**
- No code. Runs the scoped suite and records the validation procedure.

**Interfaces:**
- Consumes: all prior tasks.

- [ ] **Step 1: Run the scoped hermetic suite**

Run: `python -m pytest tests/neuro_core tests/test_qa.py tests/test_woven_qa.py tests/test_woven_synth.py tests/test_literature_config.py tests/test_literature_retriever.py tests/test_literature_precision.py tests/test_cli_literature.py tests/test_briefing_literature.py -v`
Expected: PASS (all). Investigate any failure before proceeding — do not claim done on red.

- [ ] **Step 2: Confirm flag-off is unchanged**

Run: `python -m pytest tests/test_qa.py tests/test_cli_literature.py tests/test_briefing_literature.py -v`
Expected: PASS — existing separate-mode tests are the regression lock; they must be untouched by the woven additions.

- [ ] **Step 3: A/B validation (manual, via skill)**

This is a behavior change to a benchmarked, safety-sensitive system. Before any default flip:

1. Invoke the `neuro-caseboard-ab-test` skill.
2. Run the frozen 67-Q benchmark twice: `LITERATURE_WEAVE=0` (control) vs `LITERATURE_WEAVE=1` (woven), engine otherwise identical.
3. Blinded subspecialty grading + regression detection + unsafe-output check.
4. **Length-matched grading pass** to control for the answer-length confound the 3-arm summary flagged (woven answers run longer).
5. Tune `LITERATURE_PRECISION_MIN_OVERLAP` (and, only if a length-matched rerun still shows currency gaps, `LITERATURE_RECENCY_BOOST`) based on results.
6. Ship the default flip only if there are no regressions / unsafe outputs and the woven arm holds up length-matched.

- [ ] **Step 4: Commit any docs/notes from the run** (if applicable)

```bash
git add -A
git commit -m "docs: woven literature A/B validation notes"
```

---

## Self-Review

**Spec coverage:**
- One woven narrative, single synthesis pass → Tasks 5, 6.
- Retrievals stay separate → Task 4 (retrieve-only A), Task 6 (`retrieve_records` B); synthesis merges only in Task 5.
- `[n]`/`[L#]` distinct inline + two reference lists → Task 5 (prompt + citation building), Tasks 7-9 (two lists).
- Recency tie-breaker (mechanism B) → Task 2.
- Precision gate (deterministic, concept-overlap, empty-fallback) → Task 3, wired in Task 6.
- Grounding/refusal contract (PubMed-only answers with flag; refuse if both silent) → Task 5 prompt; refusal/empty-guard in Task 6.
- C5 empty-answer guard + ambiguity Clarification short-circuit + variant prepend preserved → Task 6.
- Feature flag default off; flag-off byte-identical → Task 1 (flags, boost default 0), Task 6 (branch behind `weave` + injected-lane guard), Tasks 7-9 (narrative-optional rendering preserves separate-mode output), Task 10 (regression lock).
- Config knobs → Task 1.
- Validation (A/B, length-matched) → Task 10.
- Dossier explicitly out of scope → not planned (fast-follow per spec). ✓

**Placeholder scan:** No TBD/TODO; every code and test step shows complete content. ✓

**Type consistency:** `RetrievalBundle(question, hits, figures, images, variant)` defined in Task 4, consumed in Task 6. `WovenSynthesis(answer, citations, records)` defined in Task 5, consumed in Task 6. `GateResult(records, note)` defined in Task 3, consumed in Task 6 (`.records`). `LiteratureConfig` new fields defined in Task 1, consumed in Tasks 2/6. `LiteratureRetriever(..., recency_boost=)` defined in Task 2, consumed in Task 6. `synthesize_woven` signature consistent across Tasks 5-6. ✓
