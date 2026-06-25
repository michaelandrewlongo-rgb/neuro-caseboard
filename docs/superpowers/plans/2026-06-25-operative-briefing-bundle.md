# Operative Briefing Bundle — Plan 1: Backend Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a callable `build_briefing_bundle(query)` that turns a case query into a typed `OperativeBriefingBundle` (one-page briefing content + figures + references + full dossier + provenance), fully testable offline.

**Architecture:** A new `briefing_model.py` (Pydantic v2) defines the contract. A new `briefing_synth.py` gathers a section-aware evidence pool, numbers it (T#/L#), runs 7 concurrent Gemini-Flash section calls (all-to-all, failure-isolated), and parses the guided-prose replies into the model. A new `briefing_figures.py` selects 5–10 figures. A thin `build_briefing_bundle()` in `pipeline.py` wires the existing `parse_dictation → build_case_dossier` substrate to these. PDF rendering, API, and web are **separate later plans** (this plan stops at the Python object).

**Tech Stack:** Python 3, Pydantic v2 (already present via FastAPI), `concurrent.futures.ThreadPoolExecutor` (stdlib), the existing `neuro_core.synth_clients` / `neuro_caseboard.retrieve` / `neuro_caseboard.intake` / `neuro_caseboard.pipeline.build_case_dossier`. No new dependencies.

## Global Constraints

- **No new dependencies.** Pydantic v2 (`2.13.4`) and stdlib only.
- **Provider abstraction only** — synthesis goes through a `.generate(system, user, images)` client (the `make_synth_client` shape). Never import or hardcode Anthropic. The client is **injectable** into every synth function so tests run offline with a fake.
- **Citation namespaces stay distinct:** textbook = `T#`, PubMed = `L#`. Numbered once in the evidence packet; all 7 calls cite against that shared numbering. Never merged or renumbered.
- **No fabrication:** a claim with no resolvable source ref is marked `unsupported=True`, never dropped silently and never presented as fact.
- **Failure-safe:** a dead section call → recorded in `provenance.failed_sections`, that section empty, others land. PubMed failure → `literature_ok=False`, textbook-only briefing. No-corpus → honest degraded provenance.
- **Schema version** `BRIEFING_SCHEMA_VERSION` lives on the bundle and is part of any future cache key.
- **Testing gotchas (CLAUDE.md):** CI is pytest-only; never add `pytest-xdist -n auto`; guard any `streamlit` import with `pytest.importorskip("streamlit")` (N/A here, but keep collection clean). Fast local loop: `pytest tests/test_briefing_*.py -q`.
- **Anti-bleed preserved:** the case path already runs `guard.prune_offtarget`; do not bypass it.

---

## File Structure

- **Create** `neuro_caseboard/briefing_model.py` — Pydantic v2 models + `BRIEFING_SCHEMA_VERSION`. One responsibility: the data contract.
- **Create** `neuro_caseboard/briefing_synth.py` — evidence gathering + numbering, the 7 section prompts, the guided-prose parsers, and the concurrent orchestrator. One responsibility: query → `OperativeBriefing`.
- **Create** `neuro_caseboard/briefing_figures.py` — figure candidate retrieval, dedup, off-target reject, 5–10 selection. One responsibility: `CaseContext` → `list[BriefingFigure]`.
- **Modify** `neuro_caseboard/pipeline.py` — add `build_briefing_bundle(...)` (thin wiring) near the existing `build_case_dossier`.
- **Test** `tests/test_briefing_model.py`, `tests/test_briefing_synth.py`, `tests/test_briefing_figures.py`, `tests/test_briefing_pipeline.py`.

---

## Task 1: Pydantic data model

**Files:**
- Create: `neuro_caseboard/briefing_model.py`
- Test: `tests/test_briefing_model.py`

**Interfaces:**
- Produces: `BRIEFING_SCHEMA_VERSION: int`; models `BriefingItem`, `BriefingSection`, `TreatmentModality`, `AlgoNode`, `AlgoEdge`, `DecisionAlgorithm`, `CranialEquipment`, `SpineEquipment`, `EndovascularEquipment`, `EquipmentPlan` (discriminated union), `BriefingFigure`, `BriefingReference`, `OperativeBriefing`, `BriefingProvenance`, `OperativeBriefingBundle`. Field shapes are authoritative for every later task.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_model.py
from neuro_caseboard.briefing_model import (
    BRIEFING_SCHEMA_VERSION, BriefingItem, BriefingSection, TreatmentModality,
    DecisionAlgorithm, AlgoNode, AlgoEdge, CranialEquipment, SpineEquipment,
    EndovascularEquipment, BriefingFigure, BriefingReference, OperativeBriefing,
    BriefingProvenance, OperativeBriefingBundle,
)
import pydantic


def test_item_defaults_and_roundtrip():
    it = BriefingItem(text="secure ruptured aneurysm within 72h", source_refs=["T1", "L2"])
    assert it.priority == "high" and it.unsupported is False
    assert it.model_dump()["source_refs"] == ["T1", "L2"]


def test_equipment_discriminated_union_picks_class():
    # A dict tagged kind=spine must validate into SpineEquipment, never Cranial.
    brief = OperativeBriefing(
        title="x",
        equipment={"kind": "spine", "cage_class_sizing": ["PEEK 6mm"]},
    )
    assert isinstance(brief.equipment, SpineEquipment)
    assert brief.equipment.cage_class_sizing == ["PEEK 6mm"]


def test_bundle_schema_version_and_json_schema():
    b = OperativeBriefingBundle(
        topic="t", case={"any": "dict"}, briefing=OperativeBriefing(title="x"),
        dossier={"sections": []}, provenance=BriefingProvenance(),
    )
    assert b.schema_version == BRIEFING_SCHEMA_VERSION
    # JSON schema generation must not raise (drives TS codegen in a later plan).
    schema = OperativeBriefingBundle.model_json_schema()
    assert schema["properties"]["kind"]["default"] == "briefing"


def test_bundle_serializes_arbitrary_case_and_dossier():
    from dataclasses import dataclass
    @dataclass
    class FakeCase:
        procedure: str = "ACDF"
    b = OperativeBriefingBundle(
        topic="t", case=FakeCase(), briefing=OperativeBriefing(title="x"),
        dossier={"sections": []}, provenance=BriefingProvenance(),
    )
    dumped = b.model_dump(mode="json")
    assert dumped["case"]["procedure"] == "ACDF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_model.py -q`
Expected: FAIL — `ModuleNotFoundError: neuro_caseboard.briefing_model`.

- [ ] **Step 3: Write the model**

```python
# neuro_caseboard/briefing_model.py
"""Typed contract for the Operative Briefing Bundle (Pydantic v2).

Separate from neuro_caseboard.model.Dossier — that model stays the evidence-audit shape.
This is the one-page-briefing contract: serializes cleanly through FastAPI and feeds the
generated TypeScript types. The embedded CaseContext and Dossier are dataclasses (untouched),
so they ride along as arbitrary types with field serializers.
"""
from __future__ import annotations

import dataclasses
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

BRIEFING_SCHEMA_VERSION = 1


class BriefingItem(BaseModel):
    text: str
    priority: Literal["critical", "high", "optional"] = "high"
    source_refs: list[str] = []      # ["T1","L2"] — the hidden claim→source map
    unsupported: bool = False        # clinician-verify; never silently dropped


class BriefingSection(BaseModel):
    key: str
    title: str
    items: list[BriefingItem] = []
    note: str = ""


class TreatmentModality(BaseModel):
    name: str
    role: str = ""
    advantages: list[str] = []
    limitations: list[str] = []
    favoring: list[str] = []
    preferred: bool = False
    source_refs: list[str] = []


class AlgoNode(BaseModel):
    id: str
    label: str
    kind: Literal["decision", "action", "terminal"] = "decision"


class AlgoEdge(BaseModel):
    src: str
    dst: str
    condition: str = ""


class DecisionAlgorithm(BaseModel):
    nodes: list[AlgoNode] = []
    edges: list[AlgoEdge] = []


class CranialEquipment(BaseModel):
    kind: Literal["cranial"] = "cranial"
    head_fixation: list[str] = []
    visualization_navigation: list[str] = []
    monitoring: list[str] = []
    instruments_clips: list[str] = []
    graft_reconstruction: list[str] = []
    contingency: list[str] = []
    source_refs: list[str] = []


class SpineEquipment(BaseModel):
    kind: Literal["spine"] = "spine"
    positioning_monitoring: list[str] = []
    decompression_fusion_tools: list[str] = []
    instrumentation_system: list[str] = []
    cage_class_sizing: list[str] = []
    graft_options: list[str] = []
    navigation_robotics_fluoro: list[str] = []
    backup_salvage: list[str] = []
    source_refs: list[str] = []


class EndovascularEquipment(BaseModel):
    kind: Literal["endovascular"] = "endovascular"
    access_strategy: list[str] = []
    catheters_wires: list[str] = []
    devices: list[str] = []
    antithrombotic: list[str] = []
    closure: list[str] = []
    bailout_access_alt: list[str] = []
    source_refs: list[str] = []


EquipmentPlan = Annotated[
    CranialEquipment | SpineEquipment | EndovascularEquipment,
    Field(discriminator="kind"),
]


class BriefingFigure(BaseModel):
    fig_id: str
    image_path: str
    caption: str = ""
    citation: str = ""
    intent: str = ""            # pathology|anatomy|technique|device
    generated: bool = False     # schematic — excluded from the 5–10 textbook target
    source_n: str = ""          # T# ref


class BriefingReference(BaseModel):
    ref_id: str                 # "T1" | "L1"
    kind: Literal["textbook", "pubmed"]
    citation: str
    meta: dict = {}
    sections: list[str] = []    # section keys it supports (the support map)


class OperativeBriefing(BaseModel):
    title: str
    sections: list[BriefingSection] = []
    algorithm: DecisionAlgorithm | None = None
    modalities: list[TreatmentModality] = []
    equipment: EquipmentPlan | None = None
    unknowns: list[str] = []
    disclaimer: str = ""


class BriefingProvenance(BaseModel):
    textbook_ok: bool = True
    literature_ok: bool = True
    degraded: bool = False
    reason: str = ""
    failed_sections: list[str] = []
    model: str = ""


def _to_jsonable(v: Any) -> Any:
    # ponytail: dataclasses ride along as arbitrary types; asdict is the one conversion needed.
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return dataclasses.asdict(v)
    return v


class OperativeBriefingBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: Literal["briefing"] = "briefing"
    schema_version: int = BRIEFING_SCHEMA_VERSION
    topic: str = ""
    case: Any = None            # CaseContext dataclass (or dict in tests)
    briefing: OperativeBriefing
    figures: list[BriefingFigure] = []
    references: list[BriefingReference] = []
    dossier: Any = None         # neuro_caseboard.model.Dossier dataclass (full audit)
    provenance: BriefingProvenance

    @field_serializer("case", "dossier")
    def _ser(self, v: Any, _info):
        return _to_jsonable(v)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_model.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_model.py tests/test_briefing_model.py
git commit -m "feat(briefing): Pydantic model for the Operative Briefing Bundle"
```

---

## Task 2: Evidence gathering + T#/L# numbering

**Files:**
- Create: `neuro_caseboard/briefing_synth.py` (first slice — packet only)
- Test: `tests/test_briefing_synth.py`

**Interfaces:**
- Consumes: a text retriever with `.retrieve(query, top_n=int) -> list[EvidenceRecord]` (records expose `.text` and `.metadata` with `citation`/`book`/`page`); a `Dossier` whose sections carry `.literature` with `.citations` (each citation has `.title`, `.journal`, `.year`, `.pmid`, `.doi`, `.url`, `.n`).
- Produces:
  - `SECTION_KEYS: list[str]` = `["pathology","management","modalities","workup","technique","risks","equipment"]`
  - `SECTION_QUERIES: dict[str,str]` (intent-query templates keyed by section)
  - `@dataclass EvidencePacket` with `.textbook: list[dict]`, `.pubmed: list[dict]`, and `.prompt_block: str`
  - `gather_briefing_evidence(case, dossier, retriever) -> EvidencePacket`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_synth.py
from neuro_caseboard import briefing_synth as bs


class FakeRec:
    def __init__(self, text, citation, book="Youmans", page=10):
        self.text = text
        self.metadata = {"citation": citation, "book": book, "page": page}


class FakeRetriever:
    """Returns 1 unique record per query so the packet has stable content."""
    def __init__(self):
        self.calls = []
    def retrieve(self, query, top_n=6):
        self.calls.append(query)
        return [FakeRec(f"passage about {query[:20]}", f"Youmans p.{len(self.calls)}",
                        page=len(self.calls))]


class FakeCase:
    pathology = "ACoA aneurysm"
    procedure = "microsurgical clipping"
    def to_topic(self):
        return "ACoA aneurysm clipping"


class FakeDossier:
    sections = []  # no literature attached in this test


def test_gather_issues_one_query_per_section_and_numbers_sources():
    r = FakeRetriever()
    packet = bs.gather_briefing_evidence(FakeCase(), FakeDossier(), r)
    # one intent query per briefing section (7)
    assert len(r.calls) == len(bs.SECTION_KEYS)
    # textbook sources are numbered T1.. in order, deduped by citation
    ids = [t["ref_id"] for t in packet.textbook]
    assert ids == [f"T{i+1}" for i in range(len(ids))]
    assert "T1" in packet.prompt_block


def test_gather_dedups_identical_citations():
    class DupRetriever:
        def retrieve(self, query, top_n=6):
            return [FakeRec("same", "Youmans p.5", page=5)]
    packet = bs.gather_briefing_evidence(FakeCase(), FakeDossier(), DupRetriever())
    assert len(packet.textbook) == 1  # all 7 queries returned the same citation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_synth.py -q`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError: gather_briefing_evidence`.

- [ ] **Step 3: Write the gather slice**

```python
# neuro_caseboard/briefing_synth.py
"""Section-aware evidence gathering + the 7-call guided-prose synthesis for the briefing.

Retrieval reuses the existing textbook retriever (no second stack). The pool is numbered ONCE
(T# textbook, L# PubMed) so all 7 concurrent section calls cite against the same numbering.
Synthesis goes through an injected `.generate(system, user, images)` client — offline tests pass
a fake, exactly like woven_synth.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SECTION_KEYS = ["pathology", "management", "modalities", "workup",
                "technique", "risks", "equipment"]

# Intent-query templates — section-aware gathering so no section starves (design §5).
# {topic} is case.to_topic(); kept generic (no clinical literals) so it spans all subspecialties.
SECTION_QUERIES = {
    "pathology":  "{topic} pathophysiology natural history indication",
    "management": "{topic} management strategy decision algorithm treatment selection",
    "modalities": "{topic} treatment options comparison advantages disadvantages alternatives",
    "workup":     "{topic} preoperative workup imaging optimization labs medications",
    "technique":  "{topic} operative technique approach positioning critical steps anatomy",
    "risks":      "{topic} complications risks rescue bailout management",
    "equipment":  "{topic} equipment instrumentation devices implants adjuncts",
}


@dataclass
class EvidencePacket:
    textbook: list = field(default_factory=list)   # [{ref_id:"T1", citation, text, book, page}]
    pubmed: list = field(default_factory=list)     # [{ref_id:"L1", title, journal, year, pmid, doi, url}]
    prompt_block: str = ""                         # numbered sources rendered for the LLM


def _rec_citation(rec) -> str:
    meta = getattr(rec, "metadata", {}) or {}
    return (meta.get("citation") or "").strip() or (getattr(rec, "title", "") or "").strip()


def _collect_pubmed(dossier) -> list[dict]:
    """Flatten any attached PubMed citations across dossier sections, deduped by pmid/title."""
    out, seen = [], set()
    for sec in getattr(dossier, "sections", []) or []:
        lit = getattr(sec, "literature", None)
        for c in getattr(lit, "citations", []) or []:
            key = getattr(c, "pmid", "") or getattr(c, "title", "")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({"title": getattr(c, "title", ""), "journal": getattr(c, "journal", ""),
                        "year": getattr(c, "year", None), "pmid": getattr(c, "pmid", ""),
                        "doi": getattr(c, "doi", ""), "url": getattr(c, "url", "")})
    return out


def gather_briefing_evidence(case, dossier, retriever) -> EvidencePacket:
    """One intent query per briefing section through `retriever`, pooled with the dossier's
    PubMed citations, deduped and numbered T#/L#. Returns the packet + a rendered prompt block."""
    topic = case.to_topic()
    textbook, seen_cite = [], {}
    if retriever is not None:
        for key in SECTION_KEYS:
            q = SECTION_QUERIES[key].format(topic=topic)
            try:
                recs = retriever.retrieve(q, top_n=6) or []
            except Exception:
                recs = []
            for rec in recs:
                cite = _rec_citation(rec)
                if not cite or cite in seen_cite:
                    continue
                meta = getattr(rec, "metadata", {}) or {}
                ref_id = f"T{len(textbook) + 1}"
                seen_cite[cite] = ref_id
                textbook.append({"ref_id": ref_id, "citation": cite,
                                 "text": (getattr(rec, "text", "") or "")[:600],
                                 "book": meta.get("book", ""), "page": meta.get("page")})

    pubmed = _collect_pubmed(dossier)
    for i, p in enumerate(pubmed, 1):
        p["ref_id"] = f"L{i}"

    lines = ["TEXTBOOK SOURCES (cite as [T#]):"]
    for t in textbook:
        lines.append(f"[{t['ref_id']}] {t['citation']} — {t['text']}")
    if pubmed:
        lines.append("\nCONTEMPORARY STUDIES (cite as [L#]):")
        for p in pubmed:
            meta = ", ".join(s for s in (p.get("journal", ""), str(p.get("year") or "")) if s)
            lines.append(f"[{p['ref_id']}] {p.get('title','')} — {meta}")
    return EvidencePacket(textbook=textbook, pubmed=pubmed, prompt_block="\n".join(lines))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_synth.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_synth.py tests/test_briefing_synth.py
git commit -m "feat(briefing): section-aware evidence gathering with T#/L# numbering"
```

---

## Task 3: Guided-prose parsers

**Files:**
- Modify: `neuro_caseboard/briefing_synth.py` (append parsers)
- Test: `tests/test_briefing_synth.py` (append)

**Interfaces:**
- Consumes: the model types from Task 1.
- Produces:
  - `parse_prose_section(key, title, text) -> BriefingSection`
  - `parse_algorithm(text) -> DecisionAlgorithm | None`
  - `parse_modalities(text) -> list[TreatmentModality]`
  - `parse_equipment(text, subspecialty) -> EquipmentPlan | None`
  - `PROSE_KEYS = {"pathology","management","workup","technique","risks"}`

**Grammar (what the LLM is told to emit — defined here, enforced in Task 4 prompts):**
- Prose sections: one claim per line — `[critical|high|optional] claim text {T1, L2}`. Braces optional; a `{verify}` token (or no braces) → `unsupported=True`.
- Management appends an algorithm after a `---ALGORITHM---` line: node lines `id | kind | label`, edge lines `src -> dst | condition`.
- Modalities: blocks separated by `### Name`, then `key: value` lines (`role`, `advantages`, `limitations`, `favoring`, `preferred`, `refs`); list fields split on `;`.
- Equipment: `key: value` lines matching the chosen subspecialty schema's fields; list fields split on `;`; a `refs:` line → `source_refs`.

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_briefing_synth.py  (append)
from neuro_caseboard.briefing_model import (
    BriefingSection, DecisionAlgorithm, TreatmentModality,
    SpineEquipment, EndovascularEquipment,
)


def test_parse_prose_section_priority_and_refs():
    txt = ("[critical] Secure the aneurysm early {T1, L2}\n"
           "[high] Counsel on vasospasm risk {T3}\n"
           "[optional] Consider lumbar drain {verify}\n"
           "garbage line with no tag\n")
    sec = bs.parse_prose_section("risks", "Risks", txt)
    assert isinstance(sec, BriefingSection) and sec.key == "risks"
    assert [i.priority for i in sec.items] == ["critical", "high", "optional"]
    assert sec.items[0].source_refs == ["T1", "L2"]
    assert sec.items[2].unsupported is True  # {verify} → unsupported


def test_parse_algorithm_nodes_and_edges():
    txt = ("intro prose ignored\n"
           "---ALGORITHM---\n"
           "N1 | decision | Ruptured?\n"
           "N2 | action | Secure within 72h\n"
           "N1 -> N2 | yes\n")
    algo = bs.parse_algorithm(txt)
    assert isinstance(algo, DecisionAlgorithm)
    assert [n.id for n in algo.nodes] == ["N1", "N2"]
    assert algo.edges[0].src == "N1" and algo.edges[0].condition == "yes"


def test_parse_modalities_blocks():
    txt = ("### Microsurgical clipping\n"
           "role: durable occlusion\n"
           "advantages: durable; treats wide-neck\n"
           "limitations: invasive\n"
           "preferred: yes\n"
           "refs: T1, L2\n"
           "### Endovascular coiling\n"
           "role: less invasive\n"
           "preferred: no\n")
    mods = bs.parse_modalities(txt)
    assert [m.name for m in mods] == ["Microsurgical clipping", "Endovascular coiling"]
    assert mods[0].advantages == ["durable", "treats wide-neck"]
    assert mods[0].preferred is True and mods[1].preferred is False
    assert mods[0].source_refs == ["T1", "L2"]


def test_parse_equipment_selects_schema_by_subspecialty():
    txt = ("access_strategy: transfemoral; radial backup\n"
           "devices: flow diverter; coils\n"
           "refs: T2\n")
    eq = bs.parse_equipment(txt, "endovascular")
    assert isinstance(eq, EndovascularEquipment)
    assert eq.access_strategy == ["transfemoral", "radial backup"]
    assert eq.source_refs == ["T2"]
    # spine fields on a spine schema
    eq2 = bs.parse_equipment("cage_class_sizing: PEEK 6mm\n", "spine")
    assert isinstance(eq2, SpineEquipment) and eq2.cage_class_sizing == ["PEEK 6mm"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_synth.py -q`
Expected: FAIL — `AttributeError: parse_prose_section`.

- [ ] **Step 3: Append the parsers**

```python
# neuro_caseboard/briefing_synth.py  (append)
import re

from neuro_caseboard.briefing_model import (
    AlgoEdge, AlgoNode, BriefingItem, BriefingSection, CranialEquipment,
    DecisionAlgorithm, EndovascularEquipment, SpineEquipment, TreatmentModality,
)

PROSE_KEYS = {"pathology", "management", "workup", "technique", "risks"}

_PROSE_LINE = re.compile(r"^\[(critical|high|optional)\]\s*(.*?)\s*(\{([^}]*)\})?\s*$")
_REF_TOKEN = re.compile(r"^[TL]\d+$")
_ALGO_MARK = "---ALGORITHM---"


def _split_refs(blob: str) -> tuple[list[str], bool]:
    """Return (resolved T#/L# refs, unsupported_flag). Non-ref tokens (e.g. 'verify') or an
    empty brace → unsupported. ponytail: tolerant — unknown tokens just mean 'no real source'."""
    toks = [t.strip() for t in (blob or "").split(",") if t.strip()]
    refs = [t for t in toks if _REF_TOKEN.match(t)]
    unsupported = (not refs)  # no resolvable source → clinician-verify
    return refs, unsupported


def parse_prose_section(key: str, title: str, text: str) -> BriefingSection:
    items = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line == _ALGO_MARK:
            break  # algorithm block (management) is parsed separately
        m = _PROSE_LINE.match(line)
        if not m:
            continue  # ponytail: skip un-tagged lines rather than guess a priority
        priority, body, _, refblob = m.groups()
        refs, unsupported = _split_refs(refblob)
        if not body:
            continue
        items.append(BriefingItem(text=body, priority=priority,
                                  source_refs=refs, unsupported=unsupported))
    return BriefingSection(key=key, title=title, items=items)


def parse_algorithm(text: str):
    if _ALGO_MARK not in (text or ""):
        return None
    block = text.split(_ALGO_MARK, 1)[1]
    nodes, edges = [], []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "->" in line:
            left, _, cond = line.partition("|")
            src, _, dst = left.partition("->")
            if src.strip() and dst.strip():
                edges.append(AlgoEdge(src=src.strip(), dst=dst.strip(), condition=cond.strip()))
        elif line.count("|") >= 2:
            nid, kind, label = (p.strip() for p in line.split("|", 2))
            kind = kind if kind in ("decision", "action", "terminal") else "decision"
            if nid:
                nodes.append(AlgoNode(id=nid, label=label, kind=kind))
    return DecisionAlgorithm(nodes=nodes, edges=edges) if nodes else None


def _kv_lines(text: str) -> dict:
    out = {}
    for raw in (text or "").splitlines():
        if ":" in raw:
            k, _, v = raw.partition(":")
            out[k.strip().lower()] = v.strip()
    return out


def _as_items(v: str) -> list[str]:
    return [s.strip() for s in (v or "").split(";") if s.strip()]


def parse_modalities(text: str) -> list[TreatmentModality]:
    mods = []
    blocks = re.split(r"^###\s+", text or "", flags=re.MULTILINE)
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        name, _, rest = blk.partition("\n")
        kv = _kv_lines(rest)
        refs, _ = _split_refs(kv.get("refs", "").replace(",", ","))
        mods.append(TreatmentModality(
            name=name.strip(),
            role=kv.get("role", ""),
            advantages=_as_items(kv.get("advantages", "")),
            limitations=_as_items(kv.get("limitations", "")),
            favoring=_as_items(kv.get("favoring", "")),
            preferred=kv.get("preferred", "").strip().lower() in ("yes", "true", "1"),
            source_refs=refs,
        ))
    return mods


_EQUIP_CLASS = {"cranial": CranialEquipment, "spine": SpineEquipment,
                "endovascular": EndovascularEquipment}


def parse_equipment(text: str, subspecialty: str):
    cls = _EQUIP_CLASS.get(subspecialty)
    if cls is None:
        return None
    kv = _kv_lines(text)
    fields = {n for n in cls.model_fields if n not in ("kind", "source_refs")}
    data = {f: _as_items(kv[f]) for f in fields if f in kv}
    refs, _ = _split_refs(kv.get("refs", ""))
    return cls(source_refs=refs, **data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_synth.py -q`
Expected: PASS (all in file).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_synth.py tests/test_briefing_synth.py
git commit -m "feat(briefing): guided-prose parsers for sections/algorithm/modalities/equipment"
```

---

## Task 4: 7-call concurrent orchestrator + reference assembly

**Files:**
- Modify: `neuro_caseboard/briefing_synth.py` (append prompts + orchestrator)
- Test: `tests/test_briefing_synth.py` (append)

**Interfaces:**
- Consumes: `EvidencePacket` (Task 2), parsers (Task 3), an injected `synth_client` with `.generate(system, user, images)`.
- Produces:
  - `subspecialty_of(case) -> str` (`"cranial"|"spine"|"endovascular"`)
  - `build_section_prompt(key, packet, case, subspecialty) -> tuple[str, str]` (system, user)
  - `synthesize_briefing(case, dossier, packet, synth_client, *, subspecialty=None, max_workers=7) -> tuple[OperativeBriefing, list[BriefingReference], list[str]]` returning `(briefing, references, failed_sections)`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_briefing_synth.py  (append)
from neuro_caseboard.briefing_model import OperativeBriefing, BriefingReference


class FakeSynth:
    """Returns canned guided-prose per section, keyed by a marker in the user prompt."""
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.seen = []
    def generate(self, system, user, images):
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        self.seen.append(key)
        if key in self.fail:
            raise RuntimeError("synth down")
        if key == "modalities":
            return "### Clipping\nrole: durable\npreferred: yes\nrefs: T1\n"
        if key == "equipment":
            return "access_strategy: transfemoral\nrefs: T1\n"
        if key == "management":
            return ("[high] Treat early {T1}\n---ALGORITHM---\nN1 | decision | Ruptured?\n"
                    "N2 | action | Secure\nN1 -> N2 | yes\n")
        return f"[critical] {key} claim {{T1}}\n[optional] minor {key} note {{L1}}\n"


def _packet():
    return bs.EvidencePacket(
        textbook=[{"ref_id": "T1", "citation": "Youmans p.1", "text": "x", "book": "Youmans", "page": 1}],
        pubmed=[{"ref_id": "L1", "title": "Study", "journal": "J", "year": 2024, "pmid": "1", "doi": "", "url": ""}],
        prompt_block="...")


def test_synthesize_all_sections_land_and_refs_resolve():
    brief, refs, failed = bs.synthesize_briefing(
        FakeCase(), FakeDossier(), _packet(), FakeSynth(), subspecialty="endovascular")
    assert isinstance(brief, OperativeBriefing) and failed == []
    keys = {s.key for s in brief.sections}
    assert {"pathology", "workup", "technique", "risks", "management"} <= keys
    assert brief.modalities and brief.modalities[0].name == "Clipping"
    assert brief.equipment is not None and brief.equipment.kind == "endovascular"
    assert brief.algorithm is not None and len(brief.algorithm.nodes) == 2
    # references resolve to the packet, namespaces distinct, support map populated
    by_id = {r.ref_id: r for r in refs}
    assert by_id["T1"].kind == "textbook" and by_id["L1"].kind == "pubmed"
    assert by_id["T1"].sections  # at least one section cites T1


def test_synthesize_failure_isolation():
    brief, refs, failed = bs.synthesize_briefing(
        FakeCase(), FakeDossier(), _packet(), FakeSynth(fail=["risks"]),
        subspecialty="cranial")
    assert failed == ["risks"]
    assert all(s.key != "risks" or not s.items for s in brief.sections)  # risks empty/absent
    assert any(s.key == "technique" for s in brief.sections)             # others still land
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_synth.py -q`
Expected: FAIL — `AttributeError: synthesize_briefing`.

- [ ] **Step 3: Append prompts + orchestrator**

```python
# neuro_caseboard/briefing_synth.py  (append)
from concurrent.futures import ThreadPoolExecutor

from neuro_caseboard.briefing_model import BriefingReference, OperativeBriefing

_SECTION_TITLES = {
    "pathology": "Case & Pathology Frame", "management": "Management Strategy",
    "modalities": "Treatment Modalities", "workup": "Preoperative Workup & Optimization",
    "technique": "Operative Strategy & Technique", "risks": "Risks, Complications & Rescue",
    "equipment": "Equipment & Device Plan",
}

# What each section must emit. The prose grammar is enforced by these instructions + the parsers.
_FORMAT = {
    "prose": ("Output one claim per line: `[critical|high|optional] claim text {refs}` where refs "
              "are the bracketed source numbers, e.g. {T1, L2}. Use {verify} when no source "
              "supports the claim. No other prose, no headings."),
    "management": ("First, prose claim lines: `[critical|high|optional] text {refs}`. Then a line "
                   "`---ALGORITHM---` followed by 4–7 nodes `id | decision|action|terminal | label` "
                   "and edges `src -> dst | condition`."),
    "modalities": ("For each viable modality output a block:\n### <name>\nrole: ...\nadvantages: a; b\n"
                   "limitations: a; b\nfavoring: a; b\npreferred: yes|no\nrefs: T1, L2"),
    "equipment": ("Output `key: value` lines for THIS subspecialty's fields only "
                  "(semicolon-separated lists), plus a final `refs: T#, L#` line. Name device "
                  "CLASSES, not commercial products unless a source supports it."),
}

_SYSTEM = (
    "You are an attending neurosurgeon writing ONE section of a dense, case-specific operative "
    "briefing for another attending. Be high-yield; skip basics. Cite the bracketed source "
    "number for every substantive claim — textbook [T#], contemporary studies [L#], never merged. "
    "Never invent a citation, device, dose, threshold, or rate. If the sources do not support a "
    "specific, mark it {verify}. Do not include figures or a bibliography."
)


def subspecialty_of(case) -> str:
    """Map the case to one of the three equipment schemas via the existing profile classifier."""
    from neuro_caseboard.pipeline import classify_profile
    prof = classify_profile(case.to_topic())
    if prof == "spine":
        return "spine"
    if prof == "vascular":
        return "endovascular"
    return "cranial"   # skull_base / open / unclassified default to the cranial schema


def build_section_prompt(key: str, packet, case, subspecialty: str):
    fmt = _FORMAT.get(key, _FORMAT["prose"])
    user = (f"SECTION={key} ({_SECTION_TITLES[key]})\n"
            f"Case: {case.to_topic()}\nSubspecialty: {subspecialty}\n\n"
            f"EVIDENCE (cite these numbers only):\n{packet.prompt_block}\n\n"
            f"TASK: Write the {_SECTION_TITLES[key]} section.\n{fmt}")
    return _SYSTEM, user


def _synth_one(key, packet, case, subspecialty, synth_client):
    system, user = build_section_prompt(key, packet, case, subspecialty)
    return synth_client.generate(system, user, [])   # images unused for text synthesis


def synthesize_briefing(case, dossier, packet, synth_client, *,
                        subspecialty=None, max_workers=7):
    """Run all 7 section calls concurrently (all-to-all over `packet`), parse each into the model,
    and assemble the references + support map from the refs actually cited. Failure-isolated:
    a section whose call raises is recorded in `failed_sections` and left empty."""
    subspecialty = subspecialty or subspecialty_of(case)
    raw, failed = {}, []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_synth_one, k, packet, case, subspecialty, synth_client): k
                for k in SECTION_KEYS}
        for fut, k in ((f, futs[f]) for f in futs):
            try:
                raw[k] = fut.result()
            except Exception:
                failed.append(k)
    failed.sort(key=SECTION_KEYS.index)

    brief = OperativeBriefing(title=f"Operative Briefing — {case.to_topic()}")
    for k in SECTION_KEYS:
        text = raw.get(k, "")
        if k in PROSE_KEYS:
            brief.sections.append(parse_prose_section(k, _SECTION_TITLES[k], text))
        elif k == "modalities":
            brief.modalities = parse_modalities(text)
        elif k == "equipment":
            brief.equipment = parse_equipment(text, subspecialty)
        if k == "management":
            brief.algorithm = parse_algorithm(text)

    references = _assemble_references(brief, packet)
    return brief, references, failed


def _all_refs_with_sections(brief):
    """Yield (ref_id, section_key) for every cited ref across the briefing (the support map)."""
    for s in brief.sections:
        for it in s.items:
            for r in it.source_refs:
                yield r, s.key
    for m in brief.modalities:
        for r in m.source_refs:
            yield r, "modalities"
    if brief.equipment:
        for r in brief.equipment.source_refs:
            yield r, "equipment"


def _assemble_references(brief, packet) -> list[BriefingReference]:
    used = {}
    for ref_id, sec in _all_refs_with_sections(brief):
        used.setdefault(ref_id, set()).add(sec)
    tb = {t["ref_id"]: t for t in packet.textbook}
    pm = {p["ref_id"]: p for p in packet.pubmed}
    refs = []
    for ref_id in sorted(used, key=lambda r: (r[0], int(r[1:]))):
        secs = sorted(used[ref_id])
        if ref_id in tb:
            t = tb[ref_id]
            refs.append(BriefingReference(ref_id=ref_id, kind="textbook", citation=t["citation"],
                                          meta={"book": t["book"], "page": t["page"]}, sections=secs))
        elif ref_id in pm:
            p = pm[ref_id]
            refs.append(BriefingReference(ref_id=ref_id, kind="pubmed", citation=p.get("title", ""),
                                          meta={k: p[k] for k in ("journal", "year", "pmid", "doi", "url") if k in p},
                                          sections=secs))
        # ponytail: a ref the LLM invented that isn't in the packet is dropped here — no fabrication.
    return refs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_synth.py -q`
Expected: PASS (all in file).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_synth.py tests/test_briefing_synth.py
git commit -m "feat(briefing): 7-call concurrent synthesis + reference/support-map assembly"
```

---

## Task 5: Figure selection

**Files:**
- Create: `neuro_caseboard/briefing_figures.py`
- Test: `tests/test_briefing_figures.py`

**Interfaces:**
- Consumes: a figure retriever with `.retrieve(query, *, topic="", top_n=int) -> list[EvidenceRecord]` (metadata: `figure_path`, `caption`, `citation`, `book`, `page`, `score`); `BriefingFigure` (Task 1).
- Produces:
  - `FIGURE_INTENTS: list[str]` = `["pathology","anatomy","technique","device"]`
  - `select_briefing_figures(case, fig_retriever, *, image_available=None, min_figs=5, max_figs=10) -> tuple[list[BriefingFigure], str]` returning `(figures, insufficiency_reason)` (reason is `""` when ≥`min_figs`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_figures.py
from neuro_caseboard import briefing_figures as bf


class FRec:
    def __init__(self, path, cap="cap", cite="Youmans p.1", score=0.9):
        self.metadata = {"figure_path": path, "caption": cap, "citation": cite,
                         "book": "Youmans", "page": 1, "score": score}
    @property
    def text(self):
        return self.metadata["caption"]


class FigRetriever:
    """12 unique plates spread across the 4 intents (3 each)."""
    def retrieve(self, query, topic="", top_n=8):
        intent = query.split()[-1]
        return [FRec(f"/figs/{intent}_{i}.png", cap=f"{intent} {i}") for i in range(3)]


class FakeCase:
    pathology = "ACoA aneurysm"
    def to_topic(self):
        return "ACoA aneurysm clipping"


def test_selects_up_to_ten_unique_and_records_intent():
    figs, reason = bf.select_briefing_figures(FakeCase(), FigRetriever())
    assert 5 <= len(figs) <= 10
    assert reason == ""
    assert len({f.image_path for f in figs}) == len(figs)        # all unique
    assert all(f.intent in bf.FIGURE_INTENTS for f in figs)       # intent recorded
    assert all(f.fig_id.startswith("BF") for f in figs)


def test_dedup_and_unavailable_and_insufficiency():
    class DupRetriever:
        def retrieve(self, query, topic="", top_n=8):
            return [FRec("/figs/same.png")]   # every intent returns the same plate
    figs, reason = bf.select_briefing_figures(
        FakeCase(), DupRetriever(), image_available=lambda p: True)
    assert len(figs) == 1 and reason != ""    # <5 → explicit insufficiency reason

    # off-target / unavailable images are rejected before counting
    figs2, _ = bf.select_briefing_figures(
        FakeCase(), FigRetriever(), image_available=lambda p: "pathology" not in p)
    assert all("pathology" not in f.image_path for f in figs2)


def test_no_retriever_returns_empty_with_reason():
    figs, reason = bf.select_briefing_figures(FakeCase(), None)
    assert figs == [] and reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_figures.py -q`
Expected: FAIL — `ModuleNotFoundError: neuro_caseboard.briefing_figures`.

- [ ] **Step 3: Write the selector**

```python
# neuro_caseboard/briefing_figures.py
"""Dedicated high-yield figure selector for the briefing bundle.

Reuses the existing figure retriever (no new ranking model). Issues one intent query per axis
(pathology / anatomy / corridor / technique / device), pools candidates, drops duplicates,
unavailable, and off-target plates, then keeps the best 5–10 balancing relevance and intent
diversity. Records why each figure was selected and preserves caption + source metadata.
"""
from __future__ import annotations

from neuro_caseboard.briefing_model import BriefingFigure

FIGURE_INTENTS = ["pathology", "anatomy", "technique", "device"]
_INTENT_QUERY = {
    "pathology": "{topic} pathology imaging",
    "anatomy":   "{topic} anatomy surgical corridor",
    "technique": "{topic} operative technique steps",
    "device":    "{topic} instrumentation construct device",
}


def select_briefing_figures(case, fig_retriever, *, image_available=None,
                            min_figs=5, max_figs=10):
    """Return (figures, insufficiency_reason). reason is '' when >= min_figs were found."""
    if fig_retriever is None:
        return [], "no figure corpus available"
    topic = case.to_topic()
    # round-robin by intent so a single intent can't dominate (diversity), best score first.
    by_intent = {}
    for intent in FIGURE_INTENTS:
        q = _INTENT_QUERY[intent].format(topic=topic)
        try:
            recs = fig_retriever.retrieve(q, topic=topic, top_n=max_figs) or []
        except Exception:
            recs = []
        ranked = sorted(recs, key=lambda r: (r.metadata or {}).get("score") or 0, reverse=True)
        by_intent[intent] = ranked

    chosen, seen = [], set()
    # interleave intents: take the next-best unused plate from each intent in turn
    for rank in range(max_figs):
        for intent in FIGURE_INTENTS:
            if len(chosen) >= max_figs:
                break
            pool = by_intent.get(intent, [])
            if rank >= len(pool):
                continue
            meta = pool[rank].metadata or {}
            path = meta.get("figure_path")
            if not path or path in seen:
                continue
            if image_available is not None and not image_available(path):
                continue   # off-target / unreadable → reject before counting
            seen.add(path)
            chosen.append(BriefingFigure(
                fig_id=f"BF{len(chosen) + 1}", image_path=path,
                caption=meta.get("caption", "") or "", citation=meta.get("citation", "") or "",
                intent=intent, generated=False))
    reason = "" if len(chosen) >= min_figs else (
        f"only {len(chosen)} unique on-target figures found (min {min_figs})")
    return chosen, reason
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_figures.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_figures.py tests/test_briefing_figures.py
git commit -m "feat(briefing): high-yield figure selector (intent queries, dedup, diversity)"
```

---

## Task 6: Pipeline wiring — `build_briefing_bundle`

**Files:**
- Modify: `neuro_caseboard/pipeline.py` (add `build_briefing_bundle` + a Flash-client helper)
- Test: `tests/test_briefing_pipeline.py`

**Interfaces:**
- Consumes: `parse_dictation`/`deterministic_parse` (intake), `build_case_dossier` (existing), `gather_briefing_evidence`/`synthesize_briefing`/`subspecialty_of` (Task 2/4), `select_briefing_figures` (Task 5), all briefing models.
- Produces:
  - `briefing_synth_client(config=None)` — returns a Flash synth client (`BRIEFING_SYNTH_MODEL`, default `gemini-2.5-flash`), falling back to `make_synth_client`.
  - `build_briefing_bundle(query, *, use_llm=None, enrich=True, retriever=None, fig_retriever=None, synth_client=None, literature=None, prefs=None) -> OperativeBriefingBundle`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_pipeline.py
from neuro_caseboard.pipeline import build_briefing_bundle
from neuro_caseboard.briefing_model import OperativeBriefingBundle


class FakeSynth:
    def __init__(self, fail=()):
        self.fail = set(fail)
    def generate(self, system, user, images):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        if key in self.fail:
            raise RuntimeError("down")
        if key == "equipment":
            return "positioning_monitoring: prone; SSEP\nrefs: T1\n"
        if key == "modalities":
            return "### ACDF\nrole: decompress\npreferred: yes\nrefs: T1\n"
        return f"[critical] {key} claim {{T1}}\n"


class TRec:
    def __init__(self, n):
        self.text = f"passage {n}"
        self.metadata = {"citation": f"Youmans p.{n}", "book": "Youmans", "page": n}


class TextRetriever:
    def retrieve(self, query, top_n=6):
        return [TRec(1)]


def test_sparse_query_builds_valid_bundle_offline():
    b = build_briefing_bundle(
        "C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
        fig_retriever=None, synth_client=FakeSynth(), literature=False)
    assert isinstance(b, OperativeBriefingBundle)
    assert b.briefing.sections and b.references               # sections + resolved refs
    assert b.briefing.equipment.kind == "spine"               # subspecialty routed
    assert b.provenance.degraded is False
    # dossier (full audit) preserved alongside the briefing
    assert b.dossier is not None
    # serializes for the API
    assert b.model_dump(mode="json")["kind"] == "briefing"


def test_pubmed_failure_is_honest_not_fabricated():
    # literature=False simulates the lane being off; provenance must say so, briefing still builds.
    b = build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                              synth_client=FakeSynth(), literature=False)
    assert b.provenance.literature_ok is False
    assert all(r.kind == "textbook" for r in b.references)     # no L# fabricated


def test_failed_section_recorded_in_provenance():
    b = build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                              synth_client=FakeSynth(fail=["risks"]), literature=False)
    assert "risks" in b.provenance.failed_sections
    assert b.provenance.degraded is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_pipeline.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_briefing_bundle'`.

- [ ] **Step 3: Add the wiring to `pipeline.py`**

Add near `build_case_dossier` (after it, before `_slug`):

```python
# neuro_caseboard/pipeline.py  (append in the build section)
def briefing_synth_client(config=None):
    """A Gemini-Flash synth client for the per-section briefing calls (cheaper/faster than the
    Pro client used for woven Ask). Honors BRIEFING_SYNTH_MODEL; falls back to make_synth_client."""
    from neuro_core.config import load_config
    from neuro_core.synth_clients import make_synth_client, VertexSynthClient
    cfg = config or load_config()
    model = os.environ.get("BRIEFING_SYNTH_MODEL", "gemini-2.5-flash")
    if getattr(cfg, "synth_provider", "") == "vertex":
        return VertexSynthClient(cfg.google_cloud_project, cfg.google_cloud_location, model)
    return make_synth_client(cfg)   # non-vertex deployments use their configured client/model


def build_briefing_bundle(query, *, use_llm=None, enrich=True, retriever=None,
                          fig_retriever=None, synth_client=None, literature=None, prefs=None):
    """Query → OperativeBriefingBundle. Reuses the case substrate (parse_dictation →
    build_case_dossier), then runs the section-aware 7-call synthesis + figure selection.
    All heavy collaborators are injectable so the whole path is testable offline."""
    from neuro_caseboard.intake import parse_dictation, deterministic_parse
    from neuro_caseboard import briefing_synth as bsy
    from neuro_caseboard.briefing_figures import select_briefing_figures
    from neuro_caseboard.briefing_model import (OperativeBriefingBundle, BriefingProvenance)

    if use_llm is None:
        use_llm = llm_enabled()
    case = deterministic_parse(query) if use_llm is False else parse_dictation(query)

    # literature: None → config flag; the case dossier attaches PubMed when enabled.
    if literature is None:
        from neuro_caseboard.literature.config import load_literature_config
        literature = load_literature_config().enabled

    dossier = build_case_dossier(case, enrich=enrich, use_llm=use_llm,
                                 literature=literature, prefs=prefs, retriever=retriever,
                                 fig_retriever=fig_retriever)

    if retriever is None and enrich:
        retriever = build_retriever()
    if synth_client is None:
        synth_client = briefing_synth_client()

    packet = bsy.gather_briefing_evidence(case, dossier, retriever)
    subspec = bsy.subspecialty_of(case)
    brief, references, failed = bsy.synthesize_briefing(
        case, dossier, packet, synth_client, subspecialty=subspec)
    brief.unknowns = case.missing_critical()
    brief.disclaimer = ("Decision support only — the surgeon verifies every recommendation "
                        "against primary sources.")

    if fig_retriever is None and enrich and _figures_enabled():
        from neuro_caseboard.retrieve import build_figure_retriever
        fig_retriever = build_figure_retriever()
    figures, fig_reason = select_briefing_figures(case, fig_retriever)

    provenance = BriefingProvenance(
        textbook_ok=bool(packet.textbook),
        literature_ok=bool(literature) and bool(packet.pubmed),
        failed_sections=failed,
        degraded=bool(failed) or not packet.textbook,
        reason="; ".join(filter(None, [
            "" if packet.textbook else "no textbook evidence",
            "" if (bool(literature) and packet.pubmed) else "no contemporary literature",
            fig_reason])),
        model=os.environ.get("BRIEFING_SYNTH_MODEL", "gemini-2.5-flash"),
    )
    return OperativeBriefingBundle(
        topic=case.to_topic(), case=case, briefing=brief, figures=figures,
        references=references, dossier=dossier, provenance=provenance)
```

> Note: `literature_ok` is `False` whenever the lane was off OR returned no usable PubMed records — both are honest "no contemporary literature" states surfaced in `reason`. `build_case_dossier` already accepts `retriever=`/`fig_retriever=` (verified in `pipeline.py`), so the injected fakes flow straight through.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_pipeline.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the whole briefing suite + a fast regression scope**

Run: `pytest tests/test_briefing_model.py tests/test_briefing_synth.py tests/test_briefing_figures.py tests/test_briefing_pipeline.py tests/test_pipeline.py -q`
Expected: PASS (all). Confirms the new path doesn't regress the existing pipeline tests.

- [ ] **Step 6: Commit**

```bash
git add neuro_caseboard/pipeline.py tests/test_briefing_pipeline.py
git commit -m "feat(briefing): build_briefing_bundle pipeline wiring (offline-testable)"
```

---

## Task 7: Cross-subspecialty + negative-control tests

**Files:**
- Test: `tests/test_briefing_subspecialty.py`

**Interfaces:**
- Consumes: `build_briefing_bundle` (Task 6). No production code — this task locks in the anti-bleed guarantees so a later refactor can't silently break them.

- [ ] **Step 1: Write the tests**

```python
# tests/test_briefing_subspecialty.py
"""Profile-specificity + cross-domain leakage controls. We assert STRUCTURE and ABSENCE,
never hardcoded clinical answer text (CLAUDE.md / spec §12)."""
from neuro_caseboard.pipeline import build_briefing_bundle


class TRec:
    def __init__(self, n): self.text = f"p{n}"; self.metadata = {"citation": f"Bk p.{n}", "book": "Bk", "page": n}
class TextRetriever:
    def retrieve(self, query, top_n=6): return [TRec(1)]


class ProfiledSynth:
    """Echoes the subspecialty into equipment so we can prove routing; emits a fixed schema."""
    def generate(self, system, user, images):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        sub = "spine" if "Subspecialty: spine" in user else (
              "endovascular" if "Subspecialty: endovascular" in user else "cranial")
        if key == "equipment":
            if sub == "spine":
                return "cage_class_sizing: PEEK; instrumentation_system: pedicle screws\nrefs: T1\n"
            if sub == "endovascular":
                return "catheters_wires: 6F guide\ndevices: flow diverter\nrefs: T1\n"
            return "head_fixation: Mayfield\ninstruments_clips: aneurysm clips\nrefs: T1\n"
        if key == "modalities":
            return "### Option\nrole: x\npreferred: yes\nrefs: T1\n"
        return f"[high] {key} {{T1}}\n"


def _bundle(query):
    return build_briefing_bundle(query, use_llm=False, retriever=TextRetriever(),
                                 synth_client=ProfiledSynth(), literature=False)


def test_spine_case_uses_spine_equipment_schema():
    eq = _bundle("C5-6 ACDF").briefing.equipment
    assert eq.kind == "spine" and eq.cage_class_sizing
    # negative control: no endovascular catheter fields exist on the spine schema
    assert not hasattr(eq, "catheters_wires")


def test_endovascular_case_uses_endo_schema_no_spine_cage():
    eq = _bundle("ruptured ACoA aneurysm coiling").briefing.equipment
    assert eq.kind == "endovascular" and eq.devices
    assert not hasattr(eq, "cage_class_sizing")        # no TLIF cage in an endovascular case


def test_cranial_case_uses_cranial_schema_no_endo_catheters():
    eq = _bundle("left retrosigmoid vestibular schwannoma").briefing.equipment
    assert eq.kind == "cranial" and eq.instruments_clips
    assert not hasattr(eq, "catheters_wires")          # no endovascular catheters in open cranial
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_briefing_subspecialty.py -q`
Expected: PASS (3 passed). If any fails, the bug is in `subspecialty_of`/`classify_profile` routing — fix there, not in the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_briefing_subspecialty.py
git commit -m "test(briefing): cross-subspecialty routing + negative-control leakage guards"
```

---

## Self-Review (completed against the spec)

- **§2 decisions** — split modules (Tasks 2–6), 7 concurrent all-to-all calls (Task 4), section-aware gathering (Task 2), Pydantic (Task 1), 3 equipment schemas (Task 1, routed Task 4/7). ✓
- **§4 data model** — all listed types present (Task 1). `ClaimSourceMap` intentionally absent (folded into `source_refs` + `BriefingReference.sections`, per spec §2). ✓
- **§5 pipeline** — parse → case dossier → gather → 7 calls → merge/refs → figures → bundle (Task 6); injected `synth_client`; failure isolation + PubMed-safe (Tasks 4, 6). ✓
- **§6 figures** — 4 intent queries, dedup, off-target/unavailable reject, 5–10 with diversity, intent recorded, captions preserved, `<5` reason (Task 5). Generated-schematic exclusion: `generated=False` here; schematic attachment deferred to Plan 2 (PDF), noted below. ✓ (partial — see deferrals)
- **§11 grounding** — T#/L# distinct + numbered once (Task 2), no-fabrication ref drop (Task 4), `unsupported` flag (Task 3), unknowns line (Task 6), anti-bleed via the reused case path (Task 6/7). ✓
- **§12 testing** — schema/orchestration (Tasks 1,4,6), cross-subspecialty + negative controls (Task 7), literature failure-safe (Task 6). One-page/figure-atlas/references-render + API/UI tests belong to **Plans 2 & 3**. ✓
- **Placeholder scan** — no TBD/TODO; every code step is complete. ✓
- **Type consistency** — `synthesize_briefing` returns `(briefing, references, failed)` consumed exactly so in Task 6; `select_briefing_figures` returns `(figures, reason)` consumed so in Task 6; `EvidencePacket.textbook/pubmed/prompt_block` consistent across Tasks 2/4. ✓

**Deferred to later plans (by design, not gaps):**
- Generated decision-algorithm SVG + schematic figures that count as `generated=True` → **Plan 2** (PDF renderer owns deterministic SVG).
- One-page fit ladder, figure atlas, references page render, Signal theme → **Plan 2**.
- `POST /api/briefing(/pdf)`, caching with `schema_version`, generated TS types, Build.tsx surface → **Plan 3**.

---

## Execution Handoff

Plan 1 (backend foundation) is complete and self-contained: it produces a tested, offline-runnable
`build_briefing_bundle()`. Plans 2 (PDF) and 3 (API + Web) follow, each authored against the real
code this plan lands.
