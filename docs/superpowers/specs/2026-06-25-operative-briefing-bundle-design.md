# Operative Briefing Bundle — Design Spec

**Date:** 2026-06-25
**Surface:** Dossier / Build (NOT Ask)
**Baseline:** `master` @ `82f443a` (PRs through #73, plus #72 Ask-UX merged after #73)
**Status:** design approved; pending spec review → writing-plans

---

## 1. Goal

Refactor the Dossier / Build surface so a pathology / operation / case description yields one
**Operative Briefing Bundle** with three clearly separated surfaces:

1. **One-page operative briefing** — attending-level, dense, case-specific, no figures, no visible
   citations on the page.
2. **High-yield figure gallery** — 5–10 unique textbook figures in a bounded scrollable region;
   figure atlas pages in the PDF.
3. **References / evidence page** — textbook (`T#`) and PubMed (`L#`) kept distinct; a section-keyed
   support map resolves every hidden claim.

The existing detailed claim-card dossier + rehearsal workflow are **preserved** as a secondary,
expandable Evidence Audit view. **Ask is not touched.** `/api/build` + `/api/build/pdf` stay for
backward compatibility.

---

## 2. Decisions log (locked with the user)

| # | Decision | Choice |
|---|----------|--------|
| Module layout | Where synthesis lives | **C** — thin `build_briefing_bundle()` in `pipeline.py`; all synthesis in new `briefing_synth.py` (mirrors `woven_synth.py`). |
| Synthesis shape | One call vs many | **7 concurrent Gemini 2.5 Flash calls**, one per briefing section (guided-prose → parse, "Option B"). |
| Evidence distribution | How the pool reaches the 7 calls | **All-to-all** — every call sees the whole pooled packet. |
| Evidence gathering | How the pool is built | **Section-aware** — one intent query per briefing section (7) through the existing retriever, pooled with the dossier substrate's evidence, deduped. No second retrieval stack. |
| Claim→source link | Mapping structure | Per-claim `source_refs` (sticky-note). **No separate `ClaimSourceMap` object** — the map is the aggregation of item refs. |
| Serialization | API boundary | **Adopt Pydantic v2** for the new briefing models → FastAPI auto-serializes; TS types generated from the schema. |
| Equipment model | One flexible vs three | **Three subspecialty schemas** (open cranial / spine / endovascular) as a Pydantic discriminated union. |
| One-page enforcement | Fit ladder | **shrink font (to a legibility floor) → trim by priority → one LLM compression pass → allow page 2.** Hard ceiling **≤2 pages, always** (no export-error state). |
| PDF identity | Theme | **Signal** identity (PR #73): reuse `exec_navy.base_css(theme)` + `CASEBOARD_PDF_STYLE` (`signal` default / `print`). |

### Deliberate divergences from the original task prompt (user overrides)
- Prompt said "omit optional **before** shrinking text" → we **shrink first, then trim**.
- Prompt said "never a 2-page one-page briefing / fail with an export error" → we **allow ≤2 pages,
  no error state** (mechanically unbreakable: trimming always converges to ≤2 pages).
- These are intentional product calls by the surgeon-owner.

---

## 3. Architecture

```
User query (terse or dictation)
   │
   ▼ parse_dictation()                       [existing]
CaseContext
   │
   ▼ build_case_dossier()                    [existing — the evidence substrate]
Dossier (+ PubMed literature)
   │
   ├── evidence substrate (per-card retrieved passages + PubMed records)
   │
   ▼ gather_briefing_evidence()              [new, reuses existing retriever]
   │   7 section-intent queries  ∪  dossier evidence  → dedup → ONE pooled packet
   │
   ▼ synthesize_briefing(packet, synth_client)   [new — briefing_synth.py]
   │   7 Flash calls, concurrent (ThreadPoolExecutor), all-to-all
   │   each → its payload; a failed call → degraded section, others land
   │   merge → assign T#/L# ids, build section-keyed support map
   │
   ▼ select_briefing_figures(case)           [new — reuses figure retriever]
   │   4 intent queries → candidate pool → dedup → 5–10 figures
   │
   ▼ OperativeBriefingBundle
       briefing · figures · references · dossier (full audit) · provenance
   │
   ├──► POST /api/briefing       → cached bundle → Build.tsx
   └──► POST /api/briefing/pdf   → operative_briefing_pdf.py
            page 1: briefing (≤2 pages, Signal theme)
            page 2+: figure atlas
            final:  references / evidence
```

**Untouched:** Ask, Cards, rehearsal/preferences, `/api/build*`, the `Dossier` dataclass, the
retrieval/figure/literature lanes (reused, not reimplemented).

---

## 4. Data model — `neuro_caseboard/briefing_model.py` (Pydantic v2)

```python
BRIEFING_SCHEMA_VERSION = 1   # part of the cache key; bump on any field change

class BriefingItem(BaseModel):
    text: str
    priority: Literal["critical", "high", "optional"] = "high"
    source_refs: list[str] = []     # ["T1","T3","L2"] — the hidden claim→source map
    unsupported: bool = False       # "clinician verification required" — never silently dropped

class BriefingSection(BaseModel):   # pathology, management, workup, technique, risks
    key: str
    title: str
    items: list[BriefingItem] = []
    note: str = ""                  # e.g. case-specific unknowns line

class TreatmentModality(BaseModel):
    name: str
    role: str = ""
    advantages: list[str] = []
    limitations: list[str] = []
    favoring: list[str] = []
    preferred: bool = False
    source_refs: list[str] = []

class AlgoNode(BaseModel):
    id: str; label: str
    kind: Literal["decision", "action", "terminal"] = "decision"
class AlgoEdge(BaseModel):
    src: str; dst: str; condition: str = ""
class DecisionAlgorithm(BaseModel):
    nodes: list[AlgoNode] = []      # 4–7 → deterministic SVG
    edges: list[AlgoEdge] = []

# --- equipment: three real schemas, discriminated union on `kind` ---
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
    catheters_wires: list[str] = []     # guide / intermediate / micro + wires
    devices: list[str] = []             # balloons / stents / flow diverters / coils / embolics
    antithrombotic: list[str] = []
    closure: list[str] = []
    bailout_access_alt: list[str] = []
    source_refs: list[str] = []
EquipmentPlan = Annotated[
    CranialEquipment | SpineEquipment | EndovascularEquipment,
    Field(discriminator="kind"),
]

class BriefingFigure(BaseModel):
    fig_id: str; image_path: str; caption: str; citation: str
    intent: str = ""                # pathology|anatomy|technique|device
    generated: bool = False         # schematic — excluded from the 5–10 textbook target
    source_n: str = ""              # T# ref

class BriefingReference(BaseModel):
    ref_id: str                     # "T1" | "L1"  (namespace = prefix)
    kind: Literal["textbook", "pubmed"]
    citation: str
    meta: dict = {}                 # page/book OR journal/year/pmid/doi/url
    sections: list[str] = []        # section keys it supports (the support map)

class OperativeBriefing(BaseModel):
    title: str
    sections: list[BriefingSection] = []     # the 5 prose sections
    algorithm: DecisionAlgorithm | None = None
    modalities: list[TreatmentModality] = []
    equipment: EquipmentPlan | None = None
    unknowns: list[str] = []                 # case-specific missing facts, NOT invented
    disclaimer: str = ""

class BriefingProvenance(BaseModel):
    textbook_ok: bool = True
    literature_ok: bool = True
    degraded: bool = False
    reason: str = ""                # PHI-safe code
    failed_sections: list[str] = []
    model: str = ""                 # e.g. "gemini-2.5-flash"

class OperativeBriefingBundle(BaseModel):
    kind: Literal["briefing"] = "briefing"
    schema_version: int = BRIEFING_SCHEMA_VERSION
    topic: str = ""
    case: Any                       # CaseContext dataclass; serialized via field_serializer → dataclasses.asdict
    briefing: OperativeBriefing
    figures: list[BriefingFigure] = []
    references: list[BriefingReference] = []
    dossier: Any                    # full evidence audit; serialized via field_serializer → _dossier_dict
    provenance: BriefingProvenance
    model_config = ConfigDict(arbitrary_types_allowed=True)
```

Both embedded dataclasses (`CaseContext`, `Dossier` — untouched) serialize through Pydantic
`@field_serializer`s: `case` via `dataclasses.asdict`, `dossier` via the existing `_dossier_dict`
in `api/server.py`. Neither existing model is rewritten.

TS types are **generated from the Pydantic JSON schema** (dev step) so the browser contract can't
drift from Python.

---

## 5. Pipeline — `briefing_synth.py` + thin `build_briefing_bundle()` in `pipeline.py`

1. `parse_dictation(query)` → `CaseContext`.
2. `build_case_dossier(case)` → `Dossier` + literature (the substrate).
3. `gather_briefing_evidence(case, dossier)` — one intent query per briefing section through the
   **existing** retriever, pooled with the dossier's per-card evidence, deduped → one evidence packet.
4. `synthesize_briefing(packet, synth_client)`:
   - 7 concurrent Flash calls (`concurrent.futures.ThreadPoolExecutor`; network-bound, threads suffice).
   - **All-to-all:** identical packet to each; the prompt differs only in which section it writes.
   - Each call returns its payload (prose `BriefingSection`, `list[TreatmentModality]`, an
     `EquipmentPlan`, or a `DecisionAlgorithm` + management prose).
   - **Failure isolation:** a dead call → section recorded in `provenance.failed_sections`, rendered
     "unavailable," never fabricated. PubMed failure → `literature_ok=False`, textbook-only briefing.
   - **Provider:** the repo's existing synth-client abstraction with the Flash model id — NOT
     hardcoded Anthropic. `synth_client` is **injected** (offline-testable with a fake, like
     `woven_synth.py`).
5. Merge → assign `T#`/`L#` ids once (consistent across all 7 sections); populate each item's
   `source_refs` and each reference's `sections`.
6. `select_briefing_figures(case)` (below).
7. Assemble `OperativeBriefingBundle`.

---

## 6. Figure selection — `select_briefing_figures()`

- 4 intent queries derived from `CaseContext`: **pathology, anatomy/corridor, operative technique,
  device/construct**.
- Retrieve a larger candidate pool; dedup + near-dedup; reject unavailable / off-target; sort by
  relevance with light diversity (simple dedup + score sort).
- Select **5–10** unique textbook figures, target 10 when the corpus supports it; record `intent`
  (why selected); preserve full captions + source metadata.
- Generated schematics may be included (`generated=True`) but do **not** count toward the 5–10
  textbook target. No generic OR-setup images unless specifically relevant.
- `<5` figures only with an explicit insufficiency reason in provenance/UI.
- `ponytail: dedup + score-sort, not full MMR; add MMR only if figures come back too similar.`

---

## 7. PDF — `operative_briefing_pdf.py`

- HTML → Playwright/Chromium, A4. Signal identity via `exec_navy.base_css(theme)` +
  `CASEBOARD_PDF_STYLE` (`signal` default / `print`). One Chromium call assembles all parts with
  page-break CSS.
- **Parts:** page 1 briefing (≤2 pages) · page 2+ figure atlas (1–2 figs/page by aspect ratio,
  full captions + source labels) · final references page.
- **Page-1 builder is pure** (unit-testable offline, no Chromium). It has **no** figure or
  bibliography slots — page 1 structurally cannot carry retrieved images or visible citations.
- **Decision algorithm** = hand-rolled deterministic SVG from nodes/edges (theme-token colors, flips
  with the theme). No image hallucination, no Graphviz dependency.
- **Fit ladder** (measure rendered height in Chromium at A4):
  1. shrink font stepwise → legibility floor (**body ≈9pt**, adjustable);
  2. still over → trim by priority (`optional` first, `critical` never);
  3. still over → **one** LLM compression pass (same grounded content, tighter);
  4. still over → allow page 2; keep trimming `optional`/`high` until ≤2 pages.
  Guarantee: **≤2 pages, always.** No silent fallback to the legacy long-form PDF.
- Chromium absent → honest "renderer unavailable" error (the pure HTML builders still test offline).

---

## 8. References page — final-page renderer

- **Support map by briefing section:** background/management · modalities · workup/medications ·
  technique/anatomy · risks/rescue · equipment.
- **Textbook sources** (`T#`): book / chapter / page or figure metadata.
- **Contemporary literature** (`L#`): title, journal, year, PMID, DOI/link.
- Curated + deduped; smallest source set covering the visible briefing. References may spill a page;
  the briefing never does. The map resolves every page-1 claim with no visible markers on page 1.

---

## 9. API & caching — `api/server.py`

- Additive: `POST /api/briefing`, `POST /api/briefing/pdf`. `/api/build*` untouched.
- Pydantic models serialize themselves (no hand-rolled briefing dict); embedded `Dossier` via
  `field_serializer` reusing `_dossier_dict`.
- Response: `kind`, `build_id`, `topic`, `case`, `briefing`, `dossier` (full audit), `provenance`.
- Cache: reuse the `OrderedDict` LRU pattern as `_BRIEFING_CACHE`; key includes `schema_version` +
  build options. **The PDF endpoint serves the cached bundle** → exported == displayed.
- Figures reuse `/api/figure?path=` + `_safe_image_path` (incl. container reroot).

---

## 10. Web UI — `web/`

`Build.tsx` becomes the briefing surface:
1. case header + export button
2. one-page operative briefing preview
3. scrollable high-yield figure gallery (bounded scroll region — not the narrow right rail)
4. references / evidence summary
5. expandable full dossier / evidence audit
6. rehearsal + remembered preferences (retained)

- New components: `OperativeBriefingView`, `DecisionAlgorithmView`, `TreatmentModalitiesView`,
  `EquipmentPlanView`, `BriefingFigureGallery`, `BriefingReferences`.
- Reuse: current `DossierView` → `EvidenceAuditView` (rename + wrap, not rebuilt); figure full-size
  view reuses the existing `<dialog>` lightbox (PR #60).
- TS types generated from the Pydantic schema. Responsive + accessible; legible on mobile without
  horizontal clipping. **Ask page unchanged.**

---

## 11. Grounding & safety rules (carried from the prompt)

- Every substantive claim maps to ≥1 retrieved source via `source_refs`.
- `T#` (textbook) and `L#` (PubMed) namespaces stay distinct; never merged or renumbered.
- No visible citation markers or retrieved figures on page 1.
- Never fabricate a citation, figure, device, lab, dose, threshold, rate, or recommendation.
- Conflicting evidence: state it minimally in the briefing, explain on the references page.
- Unsupported claim → omit, or mark `unsupported=True` (clinician-verify). Never presented as fact.
- Anti-bleed guard preserved across subspecialties (reuses `guard.prune_offtarget`).
- Sparse query → pathology/procedure-level briefing + a compact `unknowns` line; no invented patient
  facts, no blocking interrogation.
- Literature lane failure-safe: PubMed down → honest textbook-only briefing + provenance flag.

---

## 12. Testing (offline deterministic fixtures; CI stays pytest-only)

- **Schema/orchestration:** sparse + dictation both → valid bundles; no section silently vanishes;
  refs resolve; degraded (textbook-only, no-corpus) honest; **Ask unchanged**.
- **Cross-subspecialty:** cranial / spine / endovascular fixtures; equipment + workup change by
  profile. Negative controls: no platelet-function test in routine spine; no TLIF cage/graft in
  endovascular; no endovascular catheters in open cranial.
- **Page invariant:** page-1 HTML has no `<img>`/bibliography; fit ladder lands ≤2 pages; atlas
  starts after the briefing; references on the final page.
- **Figures:** 5–10 unique when fixtures allow; targets 10; `<5` only with insufficiency reason;
  dedup/off-target excluded; captions survive serialization.
- **Literature:** woven not duplicated; `T#`/`L#` distinct; PubMed failure doesn't break; unsupported
  withheld.
- **API/UI:** cached PDF == displayed bundle; TS types match output; loading/error/degraded/
  empty-figure states explicit; rehearsal still works.
- Playwright / real-model / corpus tests stay optional/manual. Respect CLAUDE.md gotchas:
  `pytest.importorskip("streamlit")`, never `pytest-xdist -n auto`, scoped fast loop locally.

---

## 13. Non-goals / constraints

- Not a generic hospital handout; not a resident checklist of basic trivia.
- No hardcoded pathology-specific clinical content in deterministic templates.
- Don't merge `T#`/`L#` namespaces; no citations/figures on page 1.
- Don't remove the detailed evidence dossier or rehearsal preferences.
- No second retrieval stack.
- No silent one-page-contract violation (ceiling is the explicit ≤2-page invariant).
- No claim of success without rendered artifacts + page-count verification.

---

## 14. Final-deliverable checklist (for completion, not now)

Run full offline pytest · frontend typecheck/build/tests · render 3 PDFs (cranial/spine/endo) ·
inspect page counts + ordering · confirm ≤2-page invariant + legibility · confirm gallery scrolls ·
confirm Ask unchanged.
