# CasePrep Thrombectomy Evidence Pack Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Move the canonical right M1 thrombectomy dossier from the current blind-review score of 72/100 to a strict pass (>=75/100) by fixing evidence retrieval/ranking, evidence hierarchy, and operational rescue/eligibility output without overclaiming missing patient facts.

**Architecture:** Add a deterministic, inspectable evidence-pack layer for anterior-circulation LVO/M1 thrombectomy, integrate it before generic PubMed/corpus retrieval, then tier/filter evidence before clinical synthesis. Keep the existing procedure-first core builder, `CaseSpec` source-of-truth model, markdown dossier rendering, and deterministic eval harness; do not add an ML ranker in V1.

**Tech Stack:** Python, pytest, existing CasePrep core builder/retriever contracts, PubMed retriever, local corpus retriever, markdown/YAML dossier rendering.

---

## Current Context

- Repo: `/home/michael/projects/caseprep`
- Branch inspected: `caseprep-schema-dossier`
- Git state at planning time: clean
- Current failing clinical target: canonical case `right_m1_stroke_thrombectomy`
- Final blind-review result: `72/100`; strict pass threshold is `75/100`
- Deterministic eval currently passes, so next work must improve clinical/evidence quality rather than just concept coverage.
- Primary bottleneck from blind review: evidence retrieval/ranking and low-relevance source pollution.

Relevant current files:

- `caseprep/procedure_taxonomy.py`
  - Has `endovascular_thrombectomy` family and generic thrombectomy retrieval templates.
- `caseprep/retrieval_planning.py`
  - Builds five PubMed axes: anatomy, outcomes, technique, complications, reviews.
- `caseprep/core/builder.py`
  - Runs PubMed axes, Open-i, local corpus; tags with `surgical_usefulness_score`; synthesizes and renders.
- `caseprep/scoring.py`
  - Has transparent relevance/evidence-grade heuristics.
- `caseprep/schema.py`
  - Renders thrombectomy-specific scaffold/default sections.
- `caseprep/synthesis/section_synthesis.py`
  - Groups evidence into clinical draft sections.
- `caseprep/evaluation/canonical_cases.py`
  - Defines `THROMBECTOMY_M1` required concepts.
- `tests/test_retrieval_planning.py`, `tests/test_core_builder.py`, `tests/test_scoring.py`, `tests/test_canonical_eval.py`
  - Existing test targets to extend.

## Target State

For the canonical right M1 thrombectomy dossier:

1. `07-evidence.md` explicitly separates:
   - Practice-changing EVT evidence
   - Guidelines/consensus
   - Late-window evidence
   - Large-core conditional evidence
   - Technique/device reviews
   - Complication/rescue evidence
   - Quarantined/lower-applicability sources
   - Missing or partial landmark evidence
2. Primary clinical files are not polluted by M2-only, AI workflow, rare anomaly, historical vignette, case-report, or off-domain sources.
3. Landmark evidence rows include title, PMID or DOI, tier, applicability, and verification status.
4. Missing patient facts remain visible as `needs input` / `missing`; no eligibility or technique recommendation is silently inferred.
5. Rescue planning is algorithmic for: perforation/extravasation/SAH, ICAD/re-occlusion, tandem cervical lesion, distal embolus, symptomatic ICH, and malignant MCA edema.
6. Deterministic eval expands to check evidence hierarchy/coverage and low-relevance quarantine, not just required concept mentions.
7. Next blind clinical review target: >=75/100, ideally 78+.

---

## Non-Goals / Guardrails

- Do **not** add embeddings, learned rankers, LangChain, or a complex ML retrieval stack for V1.
- Do **not** hard-code clinical claims as if they were retrieved.
- Do **not** fabricate PubMed records, PMIDs, DOIs, or guideline citations.
- Do **not** present large-core, late-window, rescue stenting, or antiplatelet decisions as automatic.
- Do **not** add drug dosing unless it is explicitly sourced and labeled protocol-dependent.
- Do **not** let evidence-pack metadata become a substitute for retrieved/verified source text in cited claims.

---

## Evidence Pack Seed Set

Use deterministic identifiers to retrieve/verify sources. These are retrieval targets, not automatic citations unless runtime verification succeeds.

Early-window anterior-circulation EVT trials:

- MR CLEAN — PMID `25517348`, DOI `10.1056/NEJMoa1411587`
- ESCAPE — PMID `25671798`, DOI `10.1056/NEJMoa1414905`
- EXTEND-IA — PMID `25671797`, DOI `10.1056/NEJMoa1414792`
- SWIFT PRIME — PMID `25882376`, DOI `10.1056/NEJMoa1415061`
- REVASCAT — PMID `25882510`, DOI `10.1056/NEJMoa1503780`

Pooled/landmark evidence:

- HERMES collaboration patient-level meta-analysis — PMID `26898852`, DOI `10.1016/S0140-6736(16)00163-X`

Late-window trials:

- DAWN — PMID `29129157`, DOI `10.1056/NEJMoa1706442`
- DEFUSE 3 — PMID `29364767`, DOI `10.1056/NEJMoa1713973`

Large-core conditional evidence:

- RESCUE-Japan LIMIT — PMID `35138767`, DOI `10.1056/NEJMoa2118191`
- SELECT2 — PMID `36762865`, DOI `10.1056/NEJMoa2214403`
- ANGEL-ASPECT — PMID `36762852`, DOI `10.1056/NEJMoa2213379`
- TENSION — PMID `37837989`, DOI `10.1016/S0140-6736(23)02032-9`
- LASTE — PMID `38718358`, DOI `10.1056/NEJMoa2314063`

Guidelines/consensus targets:

- AHA/ASA 2019 acute ischemic stroke guideline update — PMID `31662037`, DOI `10.1161/STR.0000000000000211`
- AHA/ASA 2018 acute ischemic stroke guideline — PMID `29367334`, DOI `10.1161/STR.0000000000000158`
- Current AHA/ASA guideline if retrievable — PMID `41582814`, DOI `10.1161/STR.0000000000000513`
- ESO/ESMINT guideline targets — PMIDs `31152058`, `31165090`, `30808653`

---

## Implementation Tasks

### Task 1: Add evidence-pack data model and thrombectomy registry

**Objective:** Create a small deterministic registry of expected landmark/guideline sources for anterior-circulation LVO/M1 thrombectomy.

**Files:**

- Create: `caseprep/evidence_packs/__init__.py`
- Create: `caseprep/evidence_packs/thrombectomy.py`
- Create: `tests/test_evidence_packs.py`

**Step 1: Write failing tests**

Add tests that assert:

- A pack ID such as `anterior_circulation_lvo_m1` exists.
- Required items include MR CLEAN, ESCAPE, EXTEND-IA, SWIFT PRIME, REVASCAT, HERMES, DAWN, DEFUSE 3, at least one guideline target, and large-core conditional targets.
- Every `must_retrieve=True` item has `pmid` or `doi`.
- Every item has a non-empty `tier`, `applicability_summary`, and `query_fallback`.

Run:

```bash
pytest tests/test_evidence_packs.py -v
```

Expected first result: FAIL because the module does not exist.

**Step 2: Implement minimal data model**

Use frozen dataclasses or simple typed structures:

```python
@dataclass(frozen=True)
class EvidencePackItem:
    id: str
    title_hint: str
    tier: str
    applicability: str
    required_for: tuple[str, ...]
    pmid: str | None = None
    doi: str | None = None
    query_fallback: str = ""
    must_retrieve: bool = True
    conditional: bool = False
```

Add helpers:

```python
def get_thrombectomy_pack(pack_id: str) -> EvidencePack | None: ...
def resolve_thrombectomy_pack(case_spec: CaseSpec) -> EvidencePack | None: ...
```

**Step 3: Verify**

Run:

```bash
pytest tests/test_evidence_packs.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add caseprep/evidence_packs tests/test_evidence_packs.py
git commit -m "feat: add thrombectomy evidence pack registry"
```

---

### Task 2: Resolve evidence packs from the structured case

**Objective:** Ensure right M1/MCA thrombectomy cases select the anterior-circulation LVO/M1 evidence pack while degraded/underspecified cases do not over-specialize.

**Files:**

- Modify: `caseprep/procedure_taxonomy.py`
- Modify: `caseprep/retrieval_planning.py`
- Modify: `tests/test_retrieval_planning.py`

**Step 1: Write failing tests**

Add tests asserting:

- `mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion` resolves `anterior_circulation_lvo_m1`.
- `stroke thrombectomy` remains degraded and does not force the M1 pack.
- Existing five PubMed axes remain unchanged in order/labels.

Run:

```bash
pytest tests/test_retrieval_planning.py -v
```

Expected: FAIL for missing evidence-pack metadata.

**Step 2: Add planning metadata**

Add either:

- `evidence_pack_id` to a new retrieval-plan object, or
- `structured["retrieval"]["evidence_pack"]` later in builder from the resolved case.

Keep `build_case_queries()` simple; avoid a large refactor. Prefer a helper such as:

```python
def resolve_case_evidence_pack(case: CaseSpec, family: ProcedureFamily | None) -> str | None:
    ...
```

Rules:

- Require `endovascular_thrombectomy` family.
- Require non-degraded or high-confidence parser evidence.
- Require M1/MCA/anterior-circulation clues.
- Do not force the pack for basilar/posterior circulation or bare `stroke thrombectomy`.

**Step 3: Verify**

Run:

```bash
pytest tests/test_retrieval_planning.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add caseprep/procedure_taxonomy.py caseprep/retrieval_planning.py tests/test_retrieval_planning.py
git commit -m "feat: resolve thrombectomy evidence packs from case input"
```

---

### Task 3: Add PubMed retrieval support for forced evidence-pack items

**Objective:** Retrieve landmark records by PMID/DOI/title target before generic PubMed axes, while recording missing/partial coverage honestly.

**Files:**

- Modify: `caseprep/retrievers/pubmed.py`
- Modify: `caseprep/core/builder.py`
- Modify: `tests/test_core_builder.py`

**Step 1: Write failing tests**

Use fake retrievers. Test cases:

1. Retriever returns records for forced PMIDs; builder puts them before generic records.
2. Retriever fails/misses one forced item; builder records it under `structured["retrieval"]["evidence_pack"]["missing"]` and does not fabricate an `EvidenceRecord`.
3. Dedupe works by PMID, DOI, then normalized title.

Run:

```bash
pytest tests/test_core_builder.py -k 'evidence_pack or landmark or dedupe' -v
```

Expected: FAIL.

**Step 2: Add retrieval helper**

If `PubMedRetriever` can already search arbitrary queries, prefer a minimal helper:

```python
async def retrieve_pack_item(pubmed, item, max_results=1) -> EvidencePackRetrievalResult:
    # Prefer PMID query; fallback DOI/title query; mark missing/partial.
```

Only add `retrieve_by_pmids()` to `caseprep/retrievers/pubmed.py` if it simplifies the implementation and tests.

**Step 3: Builder integration**

In `build_core_case_plan()`:

1. Parse `case_spec` as today.
2. Resolve `retrieval_family` as today.
3. Resolve evidence pack if safe.
4. Retrieve pack items before generic axes.
5. Tag returned records with metadata:

```python
metadata.update({
    "evidence_pack_id": pack.id,
    "pack_item_id": item.id,
    "source_tier": item.tier,
    "evidence_role": item.tier,
    "applicability": item.applicability,
    "verification": "retrieved" | "partial" | "missing",
    "clinical_include": True,
})
```

6. Track missing/partial items in structured output, not as fake citations.

**Step 4: Add dedupe**

Create a small helper in `caseprep/core/builder.py` or a new module if needed:

```python
def dedupe_evidence(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    ...
```

Deduplication order:

1. PMID from metadata
2. DOI from metadata
3. normalized title

Prefer keeping the pack-tagged record if duplicates exist.

**Step 5: Verify**

Run:

```bash
pytest tests/test_core_builder.py -k 'evidence_pack or landmark or dedupe' -v
pytest tests/test_core_builder.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add caseprep/retrievers/pubmed.py caseprep/core/builder.py tests/test_core_builder.py
git commit -m "feat: retrieve and track thrombectomy landmark evidence"
```

---

### Task 4: Tier and quarantine evidence with transparent scoring

**Objective:** Make landmark/guideline evidence outrank generic or low-applicability sources and prevent noisy sources from driving clinical sections.

**Files:**

- Modify: `caseprep/scoring.py`
- Modify: `caseprep/core/builder.py`
- Modify: `tests/test_scoring.py`
- Modify: `tests/test_core_builder.py`

**Step 1: Write failing tests**

Add tests for the right M1 context:

- MR CLEAN/ESCAPE/HERMES/guideline pack records outrank AI workflow reviews and case reports.
- M2-only evidence is quarantined for routine M1 unless explicitly used as lower-applicability.
- Posterior-circulation-only evidence is not primary for anterior M1.
- Score reasons include the tier/applicability explanation.

Run:

```bash
pytest tests/test_scoring.py -v
```

Expected: FAIL.

**Step 2: Add tier boosts**

In `surgical_usefulness_score()`, add transparent boosts from metadata:

- `+50` practice-changing RCT for matching thrombectomy pack
- `+45` pooled patient-level meta-analysis
- `+40` guideline
- `+25` late-window RCT
- `+20` large-core RCT, conditional
- `+10` high-quality technique/review source

Keep all reasons explicit in `score_reasons`.

**Step 3: Add quarantine helper**

Add a helper such as:

```python
def classify_clinical_applicability(record: EvidenceRecord, case: CaseSpec, family: ProcedureFamily | None) -> tuple[bool, str | None]:
    ...
```

Quarantine when appropriate:

- M2-only paper for M1 primary evidence
- AI/imaging-workflow-only paper
- rare anomaly/case report/historical vignette
- posterior-circulation-only source for anterior M1
- non-stroke thrombectomy or non-neuro embolization

Set:

```python
metadata["clinical_include"] = False
metadata["quarantine_reason"] = "..."
```

**Step 4: Verify**

Run:

```bash
pytest tests/test_scoring.py -v
pytest tests/test_core_builder.py -k 'quarantine or evidence_pack' -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add caseprep/scoring.py caseprep/core/builder.py tests/test_scoring.py tests/test_core_builder.py
git commit -m "feat: tier and quarantine thrombectomy evidence"
```

---

### Task 5: Keep quarantined evidence out of clinical synthesis

**Objective:** Prevent low-applicability records from appearing in anatomy, operative plan, risk, or evidence-bottom-line prose as if they were primary support.

**Files:**

- Modify: `caseprep/synthesis/section_synthesis.py`
- Modify: `caseprep/core/builder.py`
- Modify: `tests/test_core_builder.py`
- Add/update renderer tests if present.

**Step 1: Write failing test**

Create a fake evidence set with:

- one high-tier pack record
- one AI-workflow source with `clinical_include=False`
- one M2-only source with `clinical_include=False`

Assert:

- clinical draft sections include the high-tier source
- clinical draft sections do not include quarantined source titles/snippets
- structured output still lists quarantined sources for appendix rendering

Run:

```bash
pytest tests/test_core_builder.py -k 'clinical_include or quarantined' -v
```

Expected: FAIL.

**Step 2: Filter before synthesis**

In `synthesize_sections()` or at the builder call site, pass only primary clinical evidence:

```python
clinical_evidence = [
    record for record in evidence
    if record.metadata.get("clinical_include", True) is not False
]
sections = synthesize_sections(topic, clinical_evidence)
```

Keep full `evidence` on `BuildCasePlanResult` for provenance/appendix.

**Step 3: Verify**

Run:

```bash
pytest tests/test_core_builder.py -k 'clinical_include or quarantined' -v
pytest tests/test_core_builder.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add caseprep/synthesis/section_synthesis.py caseprep/core/builder.py tests/test_core_builder.py
git commit -m "fix: keep quarantined evidence out of clinical synthesis"
```

---

### Task 6: Render honest evidence coverage and hierarchy

**Objective:** Update the markdown dossier so `07-evidence.md` shows landmark coverage, source tiers, applicability, verification, missing evidence, and quarantined sources.

**Files:**

- Modify: `caseprep/schema.py`
- Modify: `tests/test_canonical_eval.py`
- Add/update renderer/schema tests if present.

**Step 1: Write failing tests**

Build a fixture output with pack records and quarantined records. Assert `07-evidence.md` contains headings:

- `Landmark Evidence Coverage`
- `Practice-Changing EVT Evidence`
- `Guidelines / Consensus`
- `Late-Window Evidence`
- `Large-Core Conditional Evidence`
- `Technique and Device Evidence`
- `Quarantined / Lower-Applicability Sources`
- `Missing or Partial Evidence`

Assert primary source rows include:

- Title
- PMID or DOI
- Tier
- Applicability
- Verification status

Run:

```bash
pytest tests/test_canonical_eval.py -k evidence -v
```

Expected: FAIL.

**Step 2: Add renderer fields**

Extend the schema/renderer input to include evidence coverage from builder:

```python
schema["case"]["evidence"]["coverage"] = structured["retrieval"].get("evidence_pack", {})
schema["case"]["evidence"]["quarantined_sources"] = [...]
```

Do not label a source `cited` unless actually retrieved/verified.

**Step 3: Render conditional language**

For late-window and large-core rows, include explicit caveats:

- Applies only if time window/imaging selection supports it.
- Requires LKW/onset, ASPECTS/core, perfusion/mismatch, NIHSS/disabling deficit, baseline mRS/goals-of-care, hemorrhage risk, and local protocol.

**Step 4: Verify**

Run:

```bash
pytest tests/test_canonical_eval.py -k evidence -v
pytest tests/test_canonical_eval.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add caseprep/schema.py tests/test_canonical_eval.py
git commit -m "feat: render thrombectomy evidence coverage and hierarchy"
```

---

### Task 7: Expand thrombectomy eligibility output without overclaiming

**Objective:** Add an operational go/no-go grid that preserves missing facts and labels protocol-dependent thresholds.

**Files:**

- Modify: `caseprep/schema.py`
- Modify: `caseprep/evaluation/canonical_cases.py` if deterministic required concepts need tightening
- Modify: `tests/test_canonical_eval.py`

**Step 1: Write failing tests**

For canonical right M1 output, assert `00-morning-of-case.md` contains a go/no-go grid or checklist with:

- Last-known-well / onset category
- NIHSS / disabling deficit
- Baseline mRS / goals of care
- NCCT hemorrhage exclusion
- ASPECTS / ischemic core
- CTA-confirmed proximal anterior-circulation LVO
- CTP/MR mismatch if late/unknown window
- IV thrombolysis status
- BP framework
- Large-core caveat

Assert each patient-specific field is marked `needs input`, `missing`, or `protocol-dependent` unless it is known from the case string.

Run:

```bash
pytest tests/test_canonical_eval.py -k thrombectomy -v
```

Expected: FAIL if the grid is incomplete.

**Step 2: Implement grid in thrombectomy defaults**

Update `_thrombectomy_defaults()` / relevant rendering structure in `caseprep/schema.py`.

Use wording like:

- `Known from input: right M1 MCA occlusion / acute ischemic stroke / mechanical thrombectomy.`
- `Needs input: LKW, NIHSS, ASPECTS, core volume, collaterals, thrombolytic status, BP, baseline mRS.`
- `Protocol-dependent: numeric BP and thrombolytic thresholds; follow local stroke protocol/guideline.`

**Step 3: Verify**

Run:

```bash
pytest tests/test_canonical_eval.py -k thrombectomy -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add caseprep/schema.py caseprep/evaluation/canonical_cases.py tests/test_canonical_eval.py
git commit -m "feat: add thrombectomy eligibility go-no-go grid"
```

---

### Task 8: Upgrade rescue plans to algorithms

**Objective:** Convert named complications into practical, safety-bounded rescue algorithms.

**Files:**

- Modify: `caseprep/schema.py`
- Modify: `tests/test_canonical_eval.py`

**Step 1: Write failing tests**

Assert `05-risk-and-rescue.md` contains six algorithm headings:

- Perforation / contrast extravasation / SAH
- ICAD / fixed stenosis / re-occlusion
- Tandem cervical ICA lesion
- Distal embolus / embolus to new territory
- Symptomatic ICH
- Malignant MCA edema

For each algorithm, assert these subfields appear:

- Recognition trigger
- Stop/continue decision
- First procedural actions
- BP / antithrombotic / reversal considerations with protocol caveat
- Imaging/angiographic confirmation
- Who to notify
- Abandon/futility criteria
- Post-procedure destination/escalation

Run:

```bash
pytest tests/test_canonical_eval.py -k rescue -v
```

Expected: FAIL until fully rendered.

**Step 2: Implement algorithms**

In thrombectomy defaults, add structured rescue algorithms. Keep them operational but non-prescriptive.

Safety language required:

- Perforation: stop manipulation; prevent further injury; confirm extravasation; escalation before further device work.
- ICAD/re-occlusion: distinguish embolus vs fixed stenosis; rescue angioplasty/stenting and antiplatelets are attending/protocol decisions.
- Tandem lesion: sequence cervical/intracranial strategy depends on anatomy, collateral status, antiplatelet risk, and local protocol.
- Distal embolus: do not chase tiny distal emboli automatically; weigh territory, device risk, and achieved reperfusion.
- sICH: urgent imaging, BP/reversal protocol, ICU/neurosurgery/stroke-team escalation.
- Malignant edema: serial neuro exams/imaging, ICU, decompressive hemicraniectomy consideration for eligible patients; no automatic recommendation.

**Step 3: Verify**

Run:

```bash
pytest tests/test_canonical_eval.py -k rescue -v
pytest tests/test_canonical_eval.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add caseprep/schema.py tests/test_canonical_eval.py
git commit -m "feat: add thrombectomy rescue algorithms"
```

---

### Task 9: Expand deterministic eval gates for evidence quality

**Objective:** Make deterministic eval fail when evidence quality is polluted or landmark/guideline coverage is absent.

**Files:**

- Modify: `caseprep/evaluation/rubric.py`
- Modify: `caseprep/evaluation/canonical_cases.py`
- Modify: `tests/test_canonical_eval.py`

**Step 1: Write failing tests**

Add deterministic checks for `THROMBECTOMY_M1`:

- `caseprep.yaml` includes structured evidence coverage.
- `07-evidence.md` includes landmark coverage section.
- At least early-window RCTs, HERMES, DAWN/DEFUSE 3, large-core conditional evidence, and guideline targets are either retrieved or explicitly marked missing/partial.
- Primary evidence rows include PMID/DOI or explicit missing status.
- Quarantined source section exists.
- Low-applicability source titles do not appear in primary evidence.
- Eligibility grid and rescue algorithms exist.

Run:

```bash
pytest tests/test_canonical_eval.py -v
```

Expected: FAIL until prior rendering tasks are complete.

**Step 2: Implement rubric checks**

Extend `evaluate_case_output()` to add thrombectomy-specific checks only when `expected_family == "endovascular_thrombectomy"`.

Keep checks deterministic and text/schema based. Do not require live PubMed.

**Step 3: Verify**

Run:

```bash
pytest tests/test_canonical_eval.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add caseprep/evaluation/rubric.py caseprep/evaluation/canonical_cases.py tests/test_canonical_eval.py
git commit -m "test: gate thrombectomy evidence quality in canonical eval"
```

---

### Task 10: Run live canonical build and blind review loop

**Objective:** Produce a concrete before/after artifact and verify the strict clinical score improves beyond the pass threshold.

**Files:**

- Generated artifacts only under a new eval folder, for example:
  - `references/evals/thrombectomy-m1/iteration-006/`

**Step 1: Run targeted tests**

```bash
pytest tests/test_evidence_packs.py -v
pytest tests/test_retrieval_planning.py -v
pytest tests/test_scoring.py -v
pytest tests/test_core_builder.py -v
pytest tests/test_canonical_eval.py -v
```

Expected: all pass.

**Step 2: Run full suite**

```bash
pytest
```

Expected: all pass, or explicitly document unrelated pre-existing failures.

**Step 3: Build live canonical thrombectomy dossier**

Use the repo's current canonical build command/harness. If invoking directly, use the canonical input:

```text
mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion
```

Expected artifacts:

- `caseprep.yaml`
- `00-morning-of-case.md`
- `05-risk-and-rescue.md`
- `07-evidence.md`
- provenance/structured output

**Step 4: Inspect evidence coverage manually**

Verify in the generated output:

- Landmark trials/guidelines are either retrieved/verified or explicitly missing/partial.
- Low-applicability sources are quarantined.
- Primary clinical sections do not cite quarantined sources.
- Late-window/large-core evidence is conditional.
- Missing patient facts are still visible.

**Step 5: Run blind clinical review**

Use the saved skill/workflow:

- `/home/michael/.hermes/skills/caseprep/blind-clinical-review-loop/SKILL.md`

Acceptance target:

- Overall score: >=75/100
- Evidence quality/relevance: >=7/10
- Provenance/citation support: >=4/5
- Complications/rescue: >=12/15, ideally >=13/15
- No P0 clinical defects

**Step 6: Commit generated eval artifact references only if project convention allows**

If generated eval artifacts are meant to be tracked:

```bash
git add references/evals/thrombectomy-m1/iteration-006
 git commit -m "test: add thrombectomy evidence-pack blind eval artifacts"
```

If not tracked, document paths in the final report.

---

## Suggested Implementation Order

1. Evidence pack registry and tests.
2. Evidence-pack resolution from structured case.
3. Builder retrieval + coverage tracking + dedupe.
4. Tiering/quarantine scoring.
5. Synthesis filtering.
6. Evidence hierarchy rendering.
7. Eligibility grid.
8. Rescue algorithms.
9. Deterministic eval gate expansion.
10. Live build + blind review.

The highest-yield slice is Tasks 1-6. If time is limited, implement those first, then rerun the live eval to see whether the evidence/provenance categories clear the threshold.

---

## Validation Checklist

Before asking for blind review:

- [ ] `pytest tests/test_evidence_packs.py -v` passes.
- [ ] `pytest tests/test_retrieval_planning.py -v` passes.
- [ ] `pytest tests/test_scoring.py -v` passes.
- [ ] `pytest tests/test_core_builder.py -v` passes.
- [ ] `pytest tests/test_canonical_eval.py -v` passes.
- [ ] `pytest` full suite passes or unrelated failures are documented.
- [ ] `07-evidence.md` has a landmark coverage section.
- [ ] `caseprep.yaml` has structured evidence coverage/missing/quarantine metadata.
- [ ] Missing evidence is labeled missing/partial, not silently omitted.
- [ ] Quarantined evidence is absent from primary clinical sections.
- [ ] Eligibility grid preserves missing patient facts.
- [ ] Six rescue algorithms are rendered.
- [ ] Fresh blind review scores >=75/100.

---

## Risks and Tradeoffs

- **Risk: hard-coded pack identifiers could look like hard-coded truth.** Mitigation: treat identifiers as retrieval targets; render `retrieved`, `partial`, or `missing`, never fabricated citations.
- **Risk: PubMed retrieval by title can be noisy.** Mitigation: prefer PMID/DOI retrieval; use title fallback only with explicit partial verification.
- **Risk: evidence-pack work becomes too thrombectomy-specific.** Mitigation: isolate in `caseprep/evidence_packs/thrombectomy.py`; keep generic builder interfaces reusable.
- **Risk: deterministic eval overfits right M1.** Mitigation: keep right-M1 gates only under `expected_family == "endovascular_thrombectomy"`; add regression cases for degraded stroke thrombectomy and non-M1 targets before generalizing.
- **Risk: output becomes too long.** Mitigation: keep primary evidence concise; move quarantined/lower-applicability details to appendix.
- **Risk: rescue algorithms over-prescribe.** Mitigation: require protocol-dependent caveats and no drug dosing unless explicitly sourced.

---

## Open Questions

1. Should evidence-pack seed identifiers be tracked as source-controlled constants, or should they live in a data file such as YAML/JSON for easier clinical curation?
2. Should generated eval artifacts under `references/evals/` be committed, or remain local run evidence only?
3. How strict should deterministic eval be when PubMed/network retrieval fails: pass with explicit missing coverage, or fail because live retrieval did not verify landmarks?
4. Should current guideline targets include only AHA/ASA and ESO/ESMINT, or also SNIS/SVIN/ESMINT technical standards where available?
5. Should the first pass stop after Tasks 1-6 to test whether evidence quality alone gets >=75, or proceed through rescue/eligibility updates before the next blind review?

---

## Execution Handoff

Plan complete. Ready to execute using subagent-driven-development: dispatch a fresh implementation subagent per task, then run two-stage review after each task:

1. Spec compliance review.
2. Code quality/regression review.

Proceed only when both reviews approve and targeted tests pass.
