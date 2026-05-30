# Thrombectomy Briefing Completeness — Design (Cycle 1)

**Date:** 2026-05-30
**Status:** Approved design, ready for implementation plan
**Program:** Neuro-IR briefing clinical-content completeness (see "Program roadmap")
**Scope (this cycle):** Thrombectomy only — add a sourced `prognostic_signs`
block and a deterministic source-coverage audit. Builds the reusable machinery
that Cycles 2–6 apply to the rest of the neuro-IR family.

## Program roadmap (all three deferred workstreams)

The deferred "briefing completeness" goal spans three workstreams. They cannot
be one implementation spec — workstream 3 is N families, each with its own
clinical content and evidence packs. Decomposition:

| Cycle | Scope | Produces |
|---|---|---|
| **1 (this spec)** | Thrombectomy: `prognostic_signs` block + source-coverage audit | The complete thrombectomy exemplar **+ the reusable pattern** (schema-block contract, render helper, family-keyed audit registries) |
| 2–6 | Apply the pattern to each family: aneurysm coiling, flow diversion, AVM/dAVF embolization, carotid stenting, venous | Each family brought to the same bar (one cycle each) |

Cycle 1 is the prerequisite: it builds the machinery (prognostic-block contract
+ the source-coverage gate) that workstreams 2 and 3 reuse for every family, so
the family rollout is registration rather than bespoke work. This mirrors the
image-bank cycle: one exemplar, gold-standard, then extend.

## Problem

The thrombectomy briefing is mature — structured sections for imaging, anatomy,
operative plan (with decision tables), risk/rescue (with a rescue-trigger
table), postop, evidence, checklists, and open questions, plus a full
evidence-sourcing layer (`source_tier`, `applicability`, `verification`,
quarantine reasons). Against the target — "everything a neurosurgeon needs:
anatomy, literature, alternatives, intraop management, complications and how to
deal with them, danger zones, good/bad prognostic signs, postop and follow-up" —
two gaps remain:

1. **No structured `prognostic_signs` block.** Favorable/unfavorable outcome
   indicators exist only as scattered "favorable" mentions in prose, not as a
   modeled, sourced section.
2. **Silent source-coverage gaps.** Some claim-bearing fields render template
   content without a `source_id`, even where the evidence pack has applicable
   sources. Nothing fails when a sourceable clinical claim is left uncited.

## Goals

1. Add a `prognostic_signs` schema block (favorable / unfavorable indicators),
   each indicator cited to stable evidence-pack item IDs, rendered inline.
2. Add a deterministic source-coverage audit that fails the canonical eval when
   a sourceable clinical claim is left uncited (or holds `needs input` /
   `needs synthesis` where the evidence pack has applicable sources).
3. Build both family-agnostic (keyed off `family.id` / procedure taxonomy) so
   Cycles 2–6 reuse them.
4. Graceful behavior: a thrombectomy schema with no evidence-pack sources still
   renders (the audit only fires where applicable sources exist).

## Key decisions

- **D1 — Authored + cited content, not per-case LLM.** Prognostic indicators are
  curated clinical content (like the existing decision/rescue tables), each
  bound to stable evidence-pack item IDs (`hermes`, `dawn`, `defuse_3`,
  `select2`, `aha_asa_2019_update`, …). This matches the established pattern and
  the "traceable, not hallucinated" bar: every indicator points to a landmark
  trial/guideline already in the pack.
- **D2 — Deterministic eval gate, not an advisory report.** The audit extends
  `caseprep/evaluation/rubric.py` and appends to
  `EvalReport.deterministic_failures` so the canonical eval **fails** on a
  violation. The failure messages (section/field-named) *are* the report — no
  separate artifact (YAGNI).
- **D3 — Allow-list of sourceable fields, not every line.** Procedural
  instructions (e.g. "stop passes, lower BP") are not literature claims and are
  exempt. Only declared claim-bearing fields are audited.
- **D4 — Patient-data `needs input` is legitimate.** Missing patient-specific
  facts (NIHSS, ASPECTS, last-known-well — see `fact_validation.py`) are an
  intended state and are explicitly exempt. The audit targets *sourceable
  literature claims left uncited*, not missing patient data.
- **D5 — No file renumbering.** The rubric hardcodes `MAJOR_MARKDOWN_FILES`
  (README + 01–07). The prognostic block renders at the **top of
  `06-postop-plan.md`** (heading → "Outcome & Postop Plan"), keeping the
  canonical file set intact and placing prognosis next to postop/follow-up.

## Architecture

Two units + two integration touch-points, both built family-agnostic.

### Unit 1 — `prognostic_signs` schema block + builder

- **Schema shape** (new section under the case schema):
  ```
  prognostic_signs = {
    "favorable":   [{indicator, detail, source_ids: [pack-item-id, ...]}, ...],
    "unfavorable": [{indicator, detail, source_ids: [pack-item-id, ...]}, ...],
  }
  ```
- **Authored content (thrombectomy), keyed off `family.id`:**
  - Favorable: high ASPECTS, good collaterals, short onset→reperfusion,
    successful reperfusion (TICI 2b–3), younger age, low baseline mRS, small
    core, accessible proximal (M1/ICA-T) clot.
  - Unfavorable: low ASPECTS, poor collaterals, large core, long
    time-to-reperfusion, failed/partial reperfusion, high NIHSS with
    comorbidity, distal/tortuous access.
  - Each indicator references ≥1 stable evidence-pack item ID.
- **Provenance:** one `ProvenanceRecord` per block,
  `field_path = "prognostic_signs"`, `value_status = "generated"`,
  `source_ids = <union of cited pack item IDs>`,
  `generated_by = "caseprep"`. Enters the existing generated→verified flow.
- **Depends on:** the thrombectomy evidence pack (for valid source IDs), the
  procedure taxonomy (`family.id`).

### Unit 2 — Source-coverage audit (`caseprep/evaluation/rubric.py`)

- **`check_source_coverage(schema, rendered) -> list[str]`** — returns
  failure messages (empty = pass), appended to
  `EvalReport.deterministic_failures`.
- **Family-keyed registries:**
  - `SOURCEABLE_FIELDS[family.id]` — claim-bearing field paths that must carry a
    citation when the evidence pack has applicable sources (thrombectomy:
    `prognostic_signs.favorable/unfavorable`,
    `risk_and_rescue.likely_complications`,
    `risk_and_rescue.catastrophic_complications`, evidence-derived notes).
  - `PATIENT_DATA_EXEMPT[family.id]` — known patient-data `needs input` markers
    (NIHSS/ASPECTS/LKW) that never fail.
- **Rules:** for each sourceable field with content, fail if it has no
  `source_id`/citation ref; fail if it holds `needs input`/`needs synthesis`
  while the evidence pack has applicable sources for that topic; never fail on a
  patient-data exempt marker.
- **Depends on:** the rendered schema/markdown, the evidence pack, the procedure
  taxonomy.

### Touch-point 1 — Renderer (`schema.py` / `renderers/markdown.py`)

`_render_thrombectomy_prognostic_signs(schema)` emits a "## Prognostic Signs"
section: a two-column **Favorable | Unfavorable** table (or two labeled
subsections) with per-row source refs (PMID/DOI via the existing `_source_ref`
helpers). Rendered at the top of `06-postop-plan.md`. No other layout changes.

### Touch-point 2 — Builder (`core/builder.py`)

Populate `schema["prognostic_signs"]` for thrombectomy during the core build
(family-keyed), emit its provenance record into the existing provenance list,
and ensure the rendered output flows through `render_caseprep_files`.

## Data flow

```
evidence_packs/thrombectomy.py (stable item IDs: hermes, dawn, defuse_3, ...)
        │
        ▼
builder: prognostic_signs[family.id] = {favorable[], unfavorable[]}   (authored + cited)
        │                                   │
        ▼                                   ▼
schema.prognostic_signs              ProvenanceRecord (generated, source_ids = pack items)
        │
        ▼
_render_thrombectomy_prognostic_signs → "## Prognostic Signs" in 06-postop-plan.md
        │
        ▼
rubric.check_source_coverage(schema, rendered)
   = for SOURCEABLE_FIELDS[family]: uncited claim OR needs-input-where-evidence-exists → fail
     (PATIENT_DATA_EXEMPT[family] markers never fail)
        │
        ▼
EvalReport.deterministic_failures  → canonical eval passes/fails
```

## Error handling

| Condition | Behavior |
|---|---|
| Evidence pack has no applicable sources for a field | Audit does not fail that field (only fires where sources exist). |
| Field holds a patient-data `needs input` marker | Exempt — never fails. |
| Sourceable field has content but no citation | Fail with a section/field-named message. |
| `prognostic_signs` absent for a family without authored content | Block renders empty/omitted; audit does not invent a failure (Cycle 1 authors thrombectomy only). |
| Adding the block | No file renumbering — renders within existing `06-postop-plan.md`. |

## Testing

- **Unit — block build:** thrombectomy `prognostic_signs` has favorable +
  unfavorable entries, each with ≥1 valid pack-item `source_id`.
- **Unit — provenance:** one `ProvenanceRecord` emitted with the union of cited
  pack IDs.
- **Unit — render:** output contains "Prognostic Signs", favorable + unfavorable
  rows, and source refs; lands in the postop file.
- **Unit — audit (a):** uncited sourceable field → failure message.
- **Unit — audit (b):** legitimate patient-data `needs input` → no failure.
- **Unit — audit (c):** `needs synthesis` where the pack has sources → failure.
- **Unit — audit (d):** fully-cited section → pass.
- **Integration:** a real thrombectomy schema passes the canonical eval with the
  block present and cited; a deliberately de-cited fixture fails the eval.

## Non-goals (this cycle)

- Other neuro-IR families (Cycles 2–6).
- A separate "danger zones" block — danger-zone completeness is enforced via the
  audit on the existing anatomy-at-risk content, not a new section.
- Per-case LLM generation of prognostic content (authored + cited instead).
- Image binding for prognostic figures (the image cycle already covers imaging
  specs; not extended here).

## Open implementation notes

- Reuse existing provenance and `_source_ref`/evidence-row helpers rather than
  inventing new ones.
- Keep `SOURCEABLE_FIELDS` / `PATIENT_DATA_EXEMPT` as explicit per-family tables
  so Cycles 2–6 register entries without touching audit logic.
- Exact favorable/unfavorable indicator list and their pack-item citations to be
  finalized against the thrombectomy pack during implementation; start with the
  landmark-trial-backed indicators above.
