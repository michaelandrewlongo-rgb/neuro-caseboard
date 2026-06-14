# Query-Adaptive Variant Disambiguation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the engine conflating two named variants of one procedure (e.g. unilateral FTP vs. bifrontal decompressive craniectomy) by auto-picking the likeliest variant and naming the assumption — or asking a clarifying question when the variants are genuinely tied — all without forcing hyper-specific queries.

**Architecture:** A pre-synthesis stage inside `Engine.query()`: a **cheap gate** (curated variant-taxonomy match OR ≥2 named-variant clusters in the already-retrieved top-k) runs first; only when it trips do we spend one Vertex `query_analyze()` LLM pass that returns the variants + chosen + confidence. Confident → re-retrieve on the chosen rewrite, synthesize with a "never merge variants" directive, and deterministically prepend a bold "Assuming …" line. Low-confidence → return a `Clarification` (no briefing). Queries that don't trip the gate run **byte-identical to today** (structural no-regression). A shared `_plan_query()` keeps prose and figure selection in lockstep.

**Tech Stack:** Python 3.12, pytest, existing `neuro_core` engine (LanceDB hybrid retrieval + reranker + `synth_client.generate`), Vertex AI Gemini synth client.

**Reference:** Design spec — `docs/superpowers/specs/2026-06-14-query-adaptive-disambiguation-design.md`.

---

## File Structure

- **Create** `neuro_core/query_analyze.py` — the taxonomy (`VARIANT_AXES`), the cheap `ambiguity_gate()`, the LLM `query_analyze()`, and their dataclasses (`Gate`, `VariantRewrite`, `QueryAnalysis`) + the `CLARIFY_THRESHOLD` constant. Mirrors the self-contained, never-raises pattern of `neuro_core/live_reconcile.py`.
- **Modify** `neuro_core/synthesize.py` — add optional `variant_directive` to `synthesize()`.
- **Modify** `neuro_core/query.py` — add `Clarification` + `_Resolved`, extend `Engine.__init__` with injectable `gate_fn`/`analyze_fn`, add `_plan_query()` + `_answer()`, rewire `query()` and `select_figures()`.
- **Modify** `neuro_caseboard/cli.py` — branch `_run_ask` on `Clarification`.
- **Modify** `app/streamlit_app.py` — branch on `Clarification` (no figures/board extraction).
- **Create** `eval/ambiguous_variants.yaml` — the ambiguous-query eval set.
- **Create** `eval/textbook/disambig_eval.py` — runner + pure metric functions (conflation / over-ask / wrong-variant).
- **Create/Modify tests** under `tests/neuro_core/` and `tests/`.

Each task is TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.

---

## Task 1: Taxonomy + cheap `ambiguity_gate` (pure, no LLM)

**Files:**
- Create: `neuro_core/query_analyze.py`
- Test: `tests/neuro_core/test_query_analyze.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/neuro_core/test_query_analyze.py
from dataclasses import dataclass
from neuro_core.query_analyze import ambiguity_gate, Gate


@dataclass
class FakeHit:
    text: str


def test_gate_trips_on_taxonomy_trigger_in_question():
    # Question names the ambiguous parent procedure; passages need not.
    g = ambiguity_gate("decompressive craniectomy steps for TBI?", [])
    assert isinstance(g, Gate)
    assert g.tripped is True
    assert g.axis == "decompressive-craniectomy"


def test_gate_trips_on_two_variant_clusters_in_passages():
    # Generic question, but retrieved passages name BOTH variants of one axis.
    hits = [FakeHit("unilateral frontotemporoparietal hemicraniectomy with a large flap"),
            FakeHit("bifrontal bicoronal Kjellberg decompression in children")]
    g = ambiguity_gate("how is the bone flap fashioned?", hits)
    assert g.tripped is True
    assert g.axis == "decompressive-craniectomy"


def test_gate_clean_miss_on_unambiguous_query():
    hits = [FakeHit("the cavernous sinus contains cranial nerves III-VI")]
    g = ambiguity_gate("what are the cavernous sinus contents?", hits)
    assert g.tripped is False
    assert g.axis is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/neuro_core/test_query_analyze.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_core.query_analyze'`.

- [ ] **Step 3: Write minimal implementation**

```python
# neuro_core/query_analyze.py
"""Query-adaptive variant disambiguation.

A cheap gate decides whether a query may conflate two named VARIANTS of one
procedure (e.g. unilateral FTP vs. bifrontal decompressive craniectomy). When it
trips, query_analyze() spends one LLM pass to pick the variant + confidence.

Like live_reconcile.py, query_analyze() NEVER raises into the answer path: any
failure -> QueryAnalysis(ambiguous=False), so the normal answer always stands.
"""
import json
import re
from dataclasses import dataclass, field

# Curated neuro procedure-variant taxonomy.
#   triggers: terms in the QUESTION that name the (ambiguous) parent procedure.
#   variants: label -> key terms whose presence in retrieved passages names that variant.
VARIANT_AXES = {
    "decompressive-craniectomy": {
        "triggers": ["decompressive craniectomy", "decompressive hemicraniectomy",
                     "decompressive craniotomy", "dhc"],
        "variants": {
            "unilateral FTP hemicraniectomy":
                ["unilateral", "frontotemporoparietal", "hemicraniectomy"],
            "bifrontal (Kjellberg) decompression":
                ["bifrontal", "bicoronal", "kjellberg"],
        },
    },
    "anterior-cervical": {
        "triggers": ["anterior cervical", "acdf"],
        "variants": {
            "ACDF (discectomy and fusion)": ["discectomy", "acdf"],
            "anterior cervical corpectomy": ["corpectomy"],
        },
    },
    "pterional-approach": {
        "triggers": ["pterional", "frontotemporal approach"],
        "variants": {
            "standard pterional craniotomy": ["pterional"],
            "orbitozygomatic approach": ["orbitozygomatic"],
        },
    },
    "csf-diversion": {
        "triggers": ["csf diversion", "drain placement"],
        "variants": {
            "external ventricular drain (EVD)": ["ventriculostomy", "ventricular drain", "evd"],
            "lumbar drain": ["lumbar drain"],
        },
    },
}


@dataclass
class Gate:
    tripped: bool
    axis: str | None = None


def _norm(s):
    return (s or "").lower()


def ambiguity_gate(question, hits):
    """Cheap, no-LLM. Trips when the question names an ambiguous parent procedure
    (taxonomy trigger) OR the retrieved passages name >=2 variants of one axis."""
    q = _norm(question)
    blob = " ".join(_norm(getattr(h, "text", "")) for h in hits)
    for axis, spec in VARIANT_AXES.items():
        trigger = any(t in q for t in spec["triggers"])
        named = sum(1 for terms in spec["variants"].values()
                    if any(term in blob for term in terms))
        if trigger or named >= 2:
            return Gate(tripped=True, axis=axis)
    return Gate(tripped=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/neuro_core/test_query_analyze.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/query_analyze.py tests/neuro_core/test_query_analyze.py
git commit -m "feat(disambig): cheap variant-ambiguity gate + neuro taxonomy

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: LLM `query_analyze()` + JSON parse + fail-open

**Files:**
- Modify: `neuro_core/query_analyze.py`
- Test: `tests/neuro_core/test_query_analyze.py`

- [ ] **Step 1: Write the failing test** (append to the existing test file)

```python
from neuro_core.query_analyze import query_analyze, QueryAnalysis, VariantRewrite, CLARIFY_THRESHOLD


class FakeSynth:
    def __init__(self, reply):
        self.reply = reply
        self.captured = None

    def generate(self, system, user, images):
        self.captured = {"system": system, "user": user, "images": images}
        return self.reply


_GOOD = (
    '{"ambiguous": true, "axis": "decompressive-craniectomy",'
    ' "variants": ['
    '   {"label": "unilateral FTP hemicraniectomy", "rewrite": "unilateral FTP hemicraniectomy steps"},'
    '   {"label": "bifrontal (Kjellberg) decompression", "rewrite": "bifrontal Kjellberg decompression steps"}'
    ' ], "chosen": "unilateral FTP hemicraniectomy", "confidence": 0.86}'
)


def test_query_analyze_parses_chosen_and_confidence():
    a = query_analyze("decompressive craniectomy steps?", [], FakeSynth(_GOOD))
    assert a.ambiguous is True
    assert a.chosen.label == "unilateral FTP hemicraniectomy"
    assert a.chosen.rewrite == "unilateral FTP hemicraniectomy steps"
    assert len(a.variants) == 2
    assert a.confidence == 0.86


def test_query_analyze_handles_fenced_json():
    a = query_analyze("q", [], FakeSynth("```json\n" + _GOOD + "\n```"))
    assert a.ambiguous is True


def test_query_analyze_fails_open_on_garbage():
    a = query_analyze("q", [], FakeSynth("the model rambled, no json here"))
    assert isinstance(a, QueryAnalysis)
    assert a.ambiguous is False


def test_query_analyze_not_ambiguous_when_fewer_than_two_variants():
    reply = '{"ambiguous": true, "variants": [{"label":"x","rewrite":"x"}], "chosen":"x", "confidence":0.9}'
    a = query_analyze("q", [], FakeSynth(reply))
    assert a.ambiguous is False  # a single variant is not a conflation


def test_clarify_threshold_is_a_float_between_zero_and_one():
    assert 0.0 < CLARIFY_THRESHOLD < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/neuro_core/test_query_analyze.py -v -k analyze`
Expected: FAIL — `ImportError: cannot import name 'query_analyze'`.

- [ ] **Step 3: Write minimal implementation** (append to `neuro_core/query_analyze.py`)

```python
CLARIFY_THRESHOLD = 0.6

ANALYZE_SYSTEM_PROMPT = (
    "You disambiguate a neurosurgical question that may conflate two named VARIANTS "
    "of one procedure. Given the question and retrieved passages, return ONLY a JSON "
    "object, no prose, with keys:\n"
    '  "ambiguous": true|false — true ONLY if the passages describe >=2 distinct named variants;\n'
    '  "axis": a short label for the variant axis, or null;\n'
    '  "variants": a list of {"label": variant name, "rewrite": the question rewritten to scope ONLY that variant};\n'
    '  "chosen": the label of the variant most consistent with the question + passages, or null;\n'
    '  "confidence": 0.0-1.0 — how clearly one variant dominates (low if the passages are split evenly).\n'
)


@dataclass
class VariantRewrite:
    label: str
    rewrite: str


@dataclass
class QueryAnalysis:
    ambiguous: bool
    axis: str | None = None
    variants: list = field(default_factory=list)
    chosen: VariantRewrite | None = None
    confidence: float = 0.0


def _parse_analysis(text):
    """Parse the model reply into a QueryAnalysis, or raise ValueError."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in analyze reply")
    obj = json.loads(cleaned[start:end + 1])
    if not obj.get("ambiguous"):
        return QueryAnalysis(ambiguous=False)
    variants = [VariantRewrite(label=str(v.get("label", "")).strip(),
                               rewrite=str(v.get("rewrite", "")).strip())
                for v in (obj.get("variants") or [])
                if v.get("label") and v.get("rewrite")]
    chosen = next((v for v in variants if v.label == obj.get("chosen")), None)
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    if len(variants) < 2 or chosen is None:
        return QueryAnalysis(ambiguous=False)
    return QueryAnalysis(ambiguous=True, axis=obj.get("axis"),
                         variants=variants, chosen=chosen, confidence=conf)


def query_analyze(question, hits, synth_client):
    """One LLM pass: detect the variant axis, rewrite per variant, pick + score.
    NEVER raises: any failure -> QueryAnalysis(ambiguous=False)."""
    try:
        passages = "\n\n".join(getattr(h, "text", "") for h in hits)
        user = f"Question: {question}\n\nPassages:\n{passages}"
        reply = synth_client.generate(ANALYZE_SYSTEM_PROMPT, user, [])
        return _parse_analysis(reply)
    except Exception:
        return QueryAnalysis(ambiguous=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/neuro_core/test_query_analyze.py -v`
Expected: PASS (8 passed — Task 1 + Task 2).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/query_analyze.py tests/neuro_core/test_query_analyze.py
git commit -m "feat(disambig): LLM query_analyze with fail-open JSON parse

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `synthesize()` accepts a `variant_directive`

**Files:**
- Modify: `neuro_core/synthesize.py:88-101`
- Test: `tests/neuro_core/test_synthesize.py`

- [ ] **Step 1: Write the failing test** (append to existing `tests/neuro_core/test_synthesize.py`)

```python
def test_synthesize_appends_variant_directive_to_user_message():
    from neuro_core.synthesize import synthesize
    from neuro_core.index import Hit

    class CapSynth:
        def __init__(self):
            self.user = None

        def generate(self, system, user, images):
            self.user = user
            return "ok"

    sc = CapSynth()
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    synthesize("q", hits, [], [], sc, variant_directive="DO NOT MERGE VARIANTS")
    assert "DO NOT MERGE VARIANTS" in sc.user


def test_synthesize_without_directive_is_unchanged():
    from neuro_core.synthesize import synthesize
    from neuro_core.index import Hit

    class CapSynth:
        def __init__(self):
            self.user = None

        def generate(self, system, user, images):
            self.user = user
            return "ok"

    sc = CapSynth()
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    synthesize("q", hits, [], [], sc)
    assert "never merge" not in sc.user.lower()  # no directive injected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/neuro_core/test_synthesize.py -v -k variant_directive`
Expected: FAIL — `TypeError: synthesize() got an unexpected keyword argument 'variant_directive'`.

- [ ] **Step 3: Write minimal implementation** — edit `neuro_core/synthesize.py`

Change the signature and inject the directive just before `generate`:

```python
def synthesize(question, hits, figures, images, synth_client, variant_directive=None):
    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if variant_directive:
        user += "\n\n" + variant_directive
    answer = synth_client.generate(SYSTEM_PROMPT, user, images)
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    for f in appended:
        citations.append(Citation(n=f.source_n, book=f.book,
                                  chapter=f.chapter or "", page=f.page))
    return Synthesis(answer=answer, citations=citations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/neuro_core/test_synthesize.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/synthesize.py tests/neuro_core/test_synthesize.py
git commit -m "feat(disambig): synthesize() accepts optional variant_directive

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `Clarification` type + `_answer()` (deterministic Assuming-line)

This task adds the output type and the shared answer-builder, but does NOT yet wire the gate into `query()` (Task 5). It keeps every existing `test_query.py` test green (pure refactor of the answer body).

**Files:**
- Modify: `neuro_core/query.py:1-46` (imports + dataclasses), `query.py:158-169` (`query`/`_answer`)
- Test: `tests/neuro_core/test_query.py`, `tests/test_briefing_pdf.py`

- [ ] **Step 1: Write the failing test** (append to `tests/neuro_core/test_query.py`)

```python
from neuro_core.query import Clarification
from neuro_core.query_analyze import VariantRewrite


def test_answer_prepends_bold_assuming_line_when_variant_set(tmp_path):
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]

    def synth(question, hits, figures, images, synth_client, variant_directive=None):
        synth_client.generate("s", "u", images)
        return Synthesis(answer="Body of the answer [1].",
                         citations=[Citation(1, "B", "C", 1)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=synth)
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "unilateral FTP rewrite")
    result = eng._answer("unilateral FTP rewrite", hits, variant=vr)
    assert result.answer.startswith(
        "**Assuming unilateral FTP hemicraniectomy (most consistent with retrieved sources).**")
    assert "Body of the answer [1]." in result.answer


def test_answer_refusal_gets_no_assuming_line(tmp_path):
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]

    def refusal(question, hits, figures, images, synth_client, variant_directive=None):
        synth_client.generate("s", "u", images)
        return Synthesis(answer="Not found in the provided sources.",
                         citations=[Citation(1, "B", "C", 1)])

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=refusal)
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "x")
    result = eng._answer("x", hits, variant=vr)
    assert result.answer == "Not found in the provided sources."
    assert result.citations == []
    assert result.figures == []
```

Also add a renderer-coverage test to `tests/test_briefing_pdf.py` (proves the bold Assuming line
survives `_md_to_html` into the PDF as `<strong>`, not a literal `>` blockquote):

```python
def test_assuming_line_renders_as_bold_strong():
    from neuro_caseboard.briefing_pdf import build_briefing_html
    from neuro_core.query import QueryResult

    answer = ("**Assuming unilateral FTP hemicraniectomy (most consistent with retrieved "
              "sources).**\n\nThe flap is 12x15 cm [1].")
    html = build_briefing_html(QueryResult(answer=answer), title="DHC")
    assert "<strong>Assuming unilateral FTP hemicraniectomy" in html
    assert "&gt; Assuming" not in html  # never a literal blockquote marker
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/neuro_core/test_query.py tests/test_briefing_pdf.py -v -k "assuming or strong"`
Expected: FAIL — `ImportError: cannot import name 'Clarification'` (and `Engine` has no `_answer`).

- [ ] **Step 3: Write minimal implementation** — edit `neuro_core/query.py`

Add the import near the top (after line 13):

```python
from .query_analyze import ambiguity_gate, query_analyze, CLARIFY_THRESHOLD
```

Add dataclasses after `QueryResult` (after line 30):

```python
@dataclass
class Clarification:
    """Returned instead of a briefing when variants are genuinely tied: the engine
    asks which variant rather than guessing. No PDF is produced for this case."""
    question: str
    variants: list = field(default_factory=list)


@dataclass
class _Resolved:
    """Internal: the (possibly variant-resolved) query + its retrieved passages."""
    question: str
    top: list
    variant: object = None  # VariantRewrite | None


def _variant_directive(label):
    return (f"Answer for the variant '{label}' ONLY. If the passages blend variants, "
            "separate them — never merge steps across variants.")
```

Replace the body of `query()` (current lines 158-169) with a shared `_answer()` + a thin `query()`:

```python
    def _answer(self, question, top, variant=None):
        figures, images = self._collect_figures(question, top)
        extra = ({"variant_directive": _variant_directive(variant.label)}
                 if variant else {})
        syn = self.synth_fn(question, top, figures, images, self.synth_client, **extra)
        if is_refusal(syn.answer):
            # Synthesis abstained: figures/citations collected from retrieval are
            # spurious on a refusal — drop both (no Assuming line either).
            return QueryResult(answer=syn.answer, citations=[], figures=[])
        answer = syn.answer
        if variant:
            answer = (f"**Assuming {variant.label} (most consistent with retrieved "
                      f"sources).**\n\n" + answer)
        return QueryResult(answer=answer, citations=syn.citations, figures=figures)

    def query(self, question):
        return self._answer(question, self._retrieve(question))
```

> Note: `**extra` means the non-variant path calls `synth_fn(...)` with the exact same arguments as today, so existing `synth_fn` stubs (which don't accept `variant_directive`) keep working.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/neuro_core/test_query.py tests/test_briefing_pdf.py -v`
Expected: PASS — the 3 new tests pass AND all pre-existing `test_query.py` / `test_briefing_pdf.py` tests stay green (pure refactor).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/query.py tests/neuro_core/test_query.py tests/test_briefing_pdf.py
git commit -m "refactor(disambig): extract _answer, add Clarification + Assuming line

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Wire the disambiguation stage into `_plan_query()`

Adds the gate → analyze → resolve/clarify flow, shared by `query()` and `select_figures()`.

**Files:**
- Modify: `neuro_core/query.py` (`Engine.__init__`, add `_plan_query`, rewire `query`/`select_figures`)
- Test: `tests/neuro_core/test_query.py`

- [ ] **Step 1: Write the failing test** (append to `tests/neuro_core/test_query.py`)

```python
from neuro_core.query_analyze import Gate, QueryAnalysis


def _trip_gate(axis="decompressive-craniectomy"):
    return lambda question, hits: Gate(tripped=True, axis=axis)


def test_confident_resolves_rewrite_and_names_variant():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "unilateral FTP rewrite")
    analyze = lambda q, h, sc: QueryAnalysis(
        ambiguous=True, axis="x",
        variants=[vr, VariantRewrite("bifrontal (Kjellberg) decompression", "bifrontal rewrite")],
        chosen=vr, confidence=0.9)
    captured = {}

    def synth(question, hits, figures, images, synth_client, variant_directive=None):
        captured["question"] = question
        captured["directive"] = variant_directive
        return Synthesis(answer="Body [1].", citations=[Citation(1, "B", "C", 1)])

    index = FakeIndex(hits)
    eng = Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=synth,
                 gate_fn=_trip_gate(), analyze_fn=analyze)
    result = eng.query("decompressive craniectomy steps?")
    assert isinstance(result, QueryResult)
    assert result.answer.startswith("**Assuming unilateral FTP hemicraniectomy")
    assert captured["question"] == "unilateral FTP rewrite"       # resolved rewrite retrieved+synthesized
    assert "never merge steps across variants" in captured["directive"]
    assert index.called_with[0] == "unilateral FTP rewrite"        # re-retrieved on the rewrite


def test_low_confidence_returns_clarification_not_briefing():
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    vr1 = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    vr2 = VariantRewrite("bifrontal (Kjellberg) decompression", "bifrontal rewrite")
    analyze = lambda q, h, sc: QueryAnalysis(ambiguous=True, axis="x",
                                             variants=[vr1, vr2], chosen=vr1, confidence=0.2)
    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=capturing_synth,
                 gate_fn=_trip_gate(), analyze_fn=analyze)
    result = eng.query("decompressive craniectomy steps?")
    assert isinstance(result, Clarification)
    assert [v.label for v in result.variants] == [vr1.label, vr2.label]


def test_gate_miss_is_byte_identical_to_today():
    # No gate trip -> never calls analyze -> same path as before the feature.
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1"),
            Hit(id="b", book="B", chapter="C", page=2, text="t2")]

    def boom_analyze(q, h, sc):
        raise AssertionError("analyze must not run when the gate does not trip")

    eng = Engine(FakeConfig(), FakeEmbedder(), FakeIndex(hits), FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=capturing_synth,
                 gate_fn=lambda q, h: Gate(tripped=False), analyze_fn=boom_analyze)
    result = eng.query("normal icp?")
    assert result.answer == "ans:2:figs0"


def test_select_figures_uses_resolved_query(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"X")
    hits = [Hit(id="a", book="Rhoton", chapter="C", page=1, text="t",
                has_figure=True, caption="c", figure_path=str(png))]
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    analyze = lambda q, h, sc: QueryAnalysis(
        ambiguous=True, axis="x",
        variants=[vr, VariantRewrite("bifrontal (Kjellberg) decompression", "b rewrite")],
        chosen=vr, confidence=0.9)
    index = FakeIndex(hits)
    eng = Engine(FakeConfig(), FakeEmbedder(), index, FakeReranker(),
                 synth_client=FakeSynthClient(), synth_fn=capturing_synth,
                 gate_fn=_trip_gate(), analyze_fn=analyze)
    figs = eng.select_figures("decompressive craniectomy figure?")
    assert len(figs) == 1
    assert index.called_with[0] == "uni rewrite"   # figures selected on the resolved query
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/neuro_core/test_query.py -v -k "confident or clarification or gate_miss or resolved"`
Expected: FAIL — `Engine.__init__() got an unexpected keyword argument 'gate_fn'`.

- [ ] **Step 3: Write minimal implementation** — edit `neuro_core/query.py`

Extend `Engine.__init__` (around line 34) to accept injectable functions:

```python
    def __init__(self, config, embedder, index, reranker, synth_client,
                 synth_fn=synthesize, visual_embedder=None, visual_index=None,
                 caption_index=None, gate_fn=ambiguity_gate, analyze_fn=query_analyze):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.synth_client = synth_client
        self.synth_fn = synth_fn
        self.gate_fn = gate_fn
        self.analyze_fn = analyze_fn
        self.visual_embedder = visual_embedder
        self.visual_index = visual_index
        self.caption_index = caption_index
```

Add `_plan_query()` and rewire `query()` / `select_figures()`:

```python
    def _plan_query(self, question):
        """Shared disambiguation seam. Returns a Clarification (ask, no briefing) or
        a _Resolved (the question + passages to answer, possibly variant-resolved).
        Keeps prose (query) and figures (select_figures) on the SAME chosen variant."""
        top = self._retrieve(question)
        gate = self.gate_fn(question, top)
        if not gate.tripped:
            return _Resolved(question, top, None)
        analysis = self.analyze_fn(question, top, self.synth_client)
        if not analysis.ambiguous:
            return _Resolved(question, top, None)
        if analysis.confidence < CLARIFY_THRESHOLD:
            return Clarification(question=question, variants=analysis.variants)
        resolved = analysis.chosen.rewrite
        return _Resolved(resolved, self._retrieve(resolved), analysis.chosen)

    def query(self, question):
        plan = self._plan_query(question)
        if isinstance(plan, Clarification):
            return plan
        return self._answer(plan.question, plan.top, plan.variant)

    def select_figures(self, question):
        """Figures the system would attach, without calling synthesis (for eval).
        Runs the disambiguation gate so figures match the resolved query; on a
        clarify outcome there is no briefing, so no figures."""
        plan = self._plan_query(question)
        if isinstance(plan, Clarification):
            return []
        figures, _ = self._collect_figures(plan.question, plan.top)
        return figures
```

> Remove the old `query()` body left from Task 4 (`return self._answer(question, self._retrieve(question))`) — it's replaced by the version above. Delete the old `select_figures` body (lines ~153-156).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/neuro_core/test_query.py -v`
Expected: PASS — new wiring tests pass AND all pre-existing tests stay green (`test_select_figures_no_synthesis` still passes: question "q" with hits text "cs" does not trip the default gate, so analyze is never called and `sc.captured == {}`).

- [ ] **Step 5: Commit**

```bash
git add neuro_core/query.py tests/neuro_core/test_query.py
git commit -m "feat(disambig): wire gate->analyze->resolve/clarify via shared _plan_query

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Surface `Clarification` in the CLI and Streamlit app

**Files:**
- Modify: `neuro_caseboard/cli.py:11-28`
- Modify: `app/streamlit_app.py:58-78`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_cli.py`)

```python
def test_ask_prints_clarification(monkeypatch, capsys):
    import neuro_caseboard.cli as cli
    from neuro_core.query import Clarification
    from neuro_core.query_analyze import VariantRewrite

    clar = Clarification(question="decompressive craniectomy steps?",
                         variants=[VariantRewrite("unilateral FTP hemicraniectomy", "a"),
                                   VariantRewrite("bifrontal (Kjellberg) decompression", "b")])

    # _run_ask does `from neuro_core.query import query` at call time, so patching the
    # module attribute makes it pick up our stub.
    import neuro_core.query as q
    monkeypatch.setattr(q, "query", lambda question, force=False: clar)

    rc = cli.main(["ask", "decompressive craniectomy steps?"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ambiguous" in out.lower()
    assert "unilateral FTP hemicraniectomy" in out
    assert "bifrontal (Kjellberg) decompression" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v -k clarification`
Expected: FAIL — the current `_run_ask` calls `result.answer` on a `Clarification` (which has no `answer`) → `AttributeError`.

- [ ] **Step 3: Write minimal implementation** — edit `neuro_caseboard/cli.py`

In `_run_ask`, branch right after obtaining `result`:

```python
def _run_ask(args) -> int:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import query, Clarification
    try:
        result = query(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        return 1
    if isinstance(result, Clarification):
        print("This question is ambiguous. Did you mean one of these variants?")
        for v in result.variants:
            print(f"  - {v.label}")
        print("\nRe-ask naming the variant you want.")
        return 0
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Patch the Streamlit surface** — edit `app/streamlit_app.py`

After `result = query(q)` (line ~59), branch before any `result.answer`/`result.figures` use:

```python
        result = query(q)
        from neuro_core.query import Clarification
        if isinstance(result, Clarification):
            st.warning("This question is ambiguous. Re-ask naming one variant:")
            for v in result.variants:
                st.markdown(f"- **{v.label}**")
            st.stop()
        record(_store, [from_figure(f) for f in result.figures], label)
        st.markdown(result.answer)
        # ... rest unchanged
```

> Streamlit is verified manually (Task 7's manual gate), not unit-tested — the branch is a thin guard.

- [ ] **Step 6: Commit**

```bash
git add neuro_caseboard/cli.py app/streamlit_app.py tests/test_cli.py
git commit -m "feat(disambig): surface Clarification in CLI + Streamlit (no PDF/board)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Eval set + metric functions + runner

Pure metric functions are unit-tested; the live run (corpus + Vertex) is a documented manual gate per `fixing-pipeline-output-errors` ("prove ACTIVE on real cases").

**Files:**
- Create: `eval/ambiguous_variants.yaml`
- Create: `eval/textbook/disambig_eval.py`
- Test: `tests/test_disambig_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_disambig_eval.py
from eval.textbook.disambig_eval import conflation, wrong_variant, over_ask
from neuro_core.query import QueryResult, Clarification


def test_conflation_true_when_forbidden_term_present():
    r = QueryResult(answer="The bifrontal bicoronal incision is made ...")
    assert conflation(r, forbidden=["bifrontal", "bicoronal", "kjellberg"]) is True


def test_conflation_false_when_clean():
    r = QueryResult(answer="**Assuming unilateral FTP hemicraniectomy ...** 12x15 cm flap [1].")
    assert conflation(r, forbidden=["bifrontal", "bicoronal", "kjellberg"]) is False


def test_wrong_variant_true_when_chosen_label_absent():
    r = QueryResult(answer="A bifrontal decompression is performed ...")
    assert wrong_variant(r, expected_label="unilateral FTP hemicraniectomy") is True


def test_over_ask_true_only_for_clarification_on_unambiguous_case():
    assert over_ask(Clarification(question="q", variants=[]), expect_ambiguous=False) is True
    assert over_ask(QueryResult(answer="x"), expect_ambiguous=False) is False
    assert over_ask(Clarification(question="q", variants=[]), expect_ambiguous=True) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_disambig_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.textbook.disambig_eval'`.

- [ ] **Step 3: Write the eval set and metric functions**

Create `eval/ambiguous_variants.yaml`:

```yaml
- question: "Describe the steps of a decompressive craniectomy for traumatic brain injury."
  expect_ambiguous: true
  expected_label: "unilateral FTP hemicraniectomy"
  forbidden: ["bifrontal", "bicoronal", "kjellberg", "contralateral zygoma"]
- question: "What is the bone work for an anterior cervical procedure at C5-6?"
  expect_ambiguous: true
  expected_label: "ACDF (discectomy and fusion)"
  forbidden: []
# Non-ambiguous control cases (must NOT clarify -> over-ask guard):
- question: "What are the contents of the cavernous sinus?"
  expect_ambiguous: false
  expected_label: null
  forbidden: []
- question: "What is the normal range for intracranial pressure?"
  expect_ambiguous: false
  expected_label: null
  forbidden: []
```

Create `eval/textbook/disambig_eval.py`:

```python
"""Eval the variant-disambiguation stage: conflation / over-ask / wrong-variant.

Pure metric functions (unit-tested) + a runner that needs the live corpus + Vertex.
Run:  python -m eval.textbook.disambig_eval --set eval/ambiguous_variants.yaml
"""
import argparse

from neuro_core.query import Clarification


def _answer_text(result):
    return getattr(result, "answer", "") or ""


def conflation(result, forbidden):
    """True if the answer mentions any forbidden (other-variant) term."""
    text = _answer_text(result).lower()
    return any(term.lower() in text for term in (forbidden or []))


def wrong_variant(result, expected_label):
    """True if a briefing was produced but does not name the expected variant."""
    if isinstance(result, Clarification) or not expected_label:
        return False
    return expected_label.lower() not in _answer_text(result).lower()


def over_ask(result, expect_ambiguous):
    """True if the engine clarified on a case that should NOT be ambiguous."""
    return isinstance(result, Clarification) and not expect_ambiguous


def main():
    import yaml
    from neuro_core.query import get_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval/ambiguous_variants.yaml")
    args = ap.parse_args()
    with open(args.set) as f:
        cases = yaml.safe_load(f)

    engine = get_engine()
    n = len(cases)
    confl = over = wrong = 0
    for c in cases:
        result = engine.query(c["question"])
        is_clar = isinstance(result, Clarification)
        cf = conflation(result, c.get("forbidden"))
        oa = over_ask(result, c.get("expect_ambiguous", False))
        wv = wrong_variant(result, c.get("expected_label"))
        confl += cf
        over += oa
        wrong += wv
        tag = "CLARIFY" if is_clar else "ANSWER"
        print(f"[{tag}] {c['question'][:60]}")
        print(f"    conflation={cf} over_ask={oa} wrong_variant={wv}")
    print(f"\nconflation_rate={confl}/{n}  over_ask_rate={over}/{n}  wrong_variant_rate={wrong}/{n}")
    print("Anchor: the DHC case must show conflation=False (0 bifrontal/Kjellberg mentions).")


if __name__ == "__main__":
    main()
```

Add an empty `eval/textbook/__init__.py` and `eval/__init__.py` if they do not already exist (needed for `from eval.textbook.disambig_eval import ...`):

```bash
test -f eval/__init__.py || touch eval/__init__.py
test -f eval/textbook/__init__.py || touch eval/textbook/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_disambig_eval.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Manual ACTIVE-on-real-cases gate** (documented; needs corpus + Vertex)

Run: `python -m eval.textbook.disambig_eval --set eval/ambiguous_variants.yaml`
Expected/required outcome:
- The DHC case prints `conflation=False` (0 bifrontal/Kjellberg mentions) — the validated anchor.
- The two control cases (`cavernous sinus`, `ICP`) print `over_ask=False` (no spurious clarify).
- Record the printed `conflation_rate / over_ask_rate / wrong_variant_rate` in the PR description.

- [ ] **Step 6: Commit**

```bash
git add eval/ambiguous_variants.yaml eval/textbook/disambig_eval.py eval/__init__.py eval/textbook/__init__.py tests/test_disambig_eval.py
git commit -m "test(disambig): eval set + conflation/over-ask/wrong-variant metrics

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the whole suite:**

Run: `pytest -q`
Expected: all green (60 baseline + the new disambiguation tests). The pre-existing `tests/neuro_core/test_query.py` passing with the stage in place is the **structural no-regression proof** — non-ambiguous queries behave exactly as before.

- [ ] **Spec coverage check:** confirm each spec section maps to a task —
  detect/gate (T1), LLM analyze (T2), synthesis directive (T3), Clarification + Assuming line (T4),
  resolve + figure parity (T5), CLI/Streamlit no-PDF-on-clarify (T6), three-metric eval + no-regression (T7).
