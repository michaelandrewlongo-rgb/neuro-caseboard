# Clinical Claim Review layer + progressive Decision Card — design

*Status: DRAFT for review. Brainstorming output; no code until approved. Branch: `fix/step0-live-bugs`.*
*Companion to `OUTSIDE_REVIEW.md` "Most valuable addition" and `FIX_PLAN.md` §3–§6.*

---

## 1. Problem

A surgeon reads a long, fluent Ask answer and cannot tell which one sentence is stale, unverified,
or off-target. A citation drawer would make the *current* answer easier to inspect; it would not
stop an outdated NORDSTEN conclusion or a stale bilateral-FUS claim from being presented as the
bottom line. The product needs a layer that (a) surfaces the decision-changing claims up front,
(b) refuses to present an unverified decision-changing claim as settled, and (c) lets the reader
open the exact supporting sentence and the physical page in one click.

## 2. Key finding that shapes this design — most of it is already built, behind flags

Tracing the proposal's "missing product work" through the code on this branch:

| Ingredient | Status | Site |
|---|---|---|
| Verbatim-quote / click-to-quote verification | **Built, flag `EVIDENCE_SPANS`** | `evidence_spans.py`, `qa.py:227` |
| Decision furniture (threshold+units, comparator, exclusions, effect size+CI) | **Built, flag `PROMPT_DECISION_FURNITURE`** | `woven_synth.py:43` |
| Calibrated language + inline date-stamp | **Built, same flag** | `woven_synth.py:48` |
| Openable folio (`printed_page`) | **Built (ingest+cite)** | `ce321ab`, `f666d0c` |
| `[D#]` currency lane + 10-subspecialty router | **Built** | `1c707e7`; `corpus` serialized to API |
| Entity-bleed check (model-free) | **Built** | `entailment.unsupported_entities` |
| Per-claim entailment + `groundedness=None` fix | **Built** | `answer_verify.verify_answer` |

**The genuinely-new work is three things, not a new engine:**

1. **Transport** — `evidence_spans` is produced (`qa.py:229`) then **dropped**: the `/api/ask` response
   (`server.py:555`) and every stream event omit it. `_citation_dict` (`server.py:332`) exposes the
   PDF `page`, not the folio, no page-image URL, no chunk text. The sidecar dies at the engine
   boundary. *(This is the CLAUDE.md silent-propagation failure class: produced, not propagated,
   nothing errors.)*
2. **The Clinical Claim Review gate** — a deterministic layer between synthesis and display that
   extracts management claims, requires each to have a matching evidence span, runs freshness /
   coverage / same-domain checks, and **softens or withholds** a decision-changing claim that fails,
   showing an explicit amber "verify current guidance" line instead. Does not exist.
3. **The progressive Decision Card render** — Bottom line → what changes the decision → uncertainties
   → expandable prose → click a `[n]` for the quoted span beside the rendered page image. Does not exist.

## 3. Scope (chosen: "full proposal as written")

All three lanes (`[n]` textbook, `[L#]` PubMed, `[D#]` corpus) unified into one Decision Card, with
active withholding of unverified decision-changing claims. **Gated by `FIX_PLAN` §6 validation
before it becomes a default** — everything ships behind a flag; no default is flipped in this work.

### Non-negotiable constraints (inherited)

- **Failure-safe / additive.** Gate off, or gate raises, → today's answer, byte-identical. Verification
  is never allowed to block or blank an answer (mirrors `evidence_spans.extract_and_verify`'s `[]`-on-error).
- **Flag-gated, default OFF.** New flag `DECISION_CARD`. Do not flip `EVIDENCE_SPANS` /
  `PROMPT_DECISION_FURNITURE` / `CORPUS_RETRIEVAL` defaults here — that is a §6 grading decision.
- **Quotes never enter prose** (§3.3.1). The verbatim quote is a verification artifact in the sidecar;
  the Decision Card's "bottom line" and prose are the model's own words with `[n]` markers only.
- **Deterministic where possible; no new LLM cost beyond the one extraction pass already in
  `evidence_spans`.** Freshness / coverage / same-domain checks are model-free. (Cost note per user
  preference: the gate adds **zero** new paid calls when `EVIDENCE_SPANS` is already on — it reuses
  that pass; +1 extraction call/answer if run standalone.)
- **`Wrong is strictly worse than absent`.** A withheld claim shows an honest amber line; it never
  shows a confidently-wrong settled claim.

## 4. Architecture

One new module, one gate call site, additive transport, one render. Data flows one direction:

```
qa._answer_question_woven
  └─ synth (woven, [n]/[L#]/[D#])           ← unchanged
  └─ verify_answer  → AnswerVerification     ← built (bleed + entailment)
  └─ extract_and_verify → [EvidenceSpan]     ← built (EVIDENCE_SPANS)
  └─ NEW: claim_review.build_decision_card(  ← the gate; deterministic
             answer, premises_meta, spans, verification)
         → DecisionCard
  └─ QAResult(..., decision_card=…, evidence_spans=…)
      └─ /api/ask + stream  (NEW: serialize both)     ← transport
          └─ web AnswerView → Decision Card render     ← progressive UI
```

### 4.1 Architectural decision: where the gate lives, and how "independent" it is

**Chosen — Approach A: a deterministic `claim_review.py` module called after synthesis, reusing the
already-built extraction + verification, adding model-free freshness/coverage/same-domain checks.**

- *Alternative B — fold it into the synthesis prompt* (ask the model to self-assess freshness and emit
  the card). Rejected: a model grading its own answer's currency is the exact self-deception `FIX_PLAN`
  §6 warns against; the whole point is an *independent* layer that can refuse.
- *Alternative C — a second LLM judge pass reviews the answer.* Rejected for the gate: non-deterministic,
  adds paid latency per answer, and duplicates the §6 judge apparatus. The already-built verbatim-quote
  match gives precision-1.0 fabrication detection for free; the LLM judge belongs in §6 validation, not
  in the live request path.

Approach A keeps the live gate deterministic and testable, uses the LLM only for the extraction pass
that already exists, and stays failure-safe.

## 5. The gate — `neuro_caseboard/claim_review.py` (new)

Pure function, no I/O, no network. Input is what the pipeline already computed; output is a
`DecisionCard`. Five steps mirror the proposal.

```python
@dataclass
class ReviewedClaim:
    text: str                 # the claim sentence (model's words, markers stripped for display)
    markers: list[str]        # ["2", "L3", "D1"]
    category: str             # indication|contraindication|threshold|comparative|regulatory|trial|other
    quote: str                # verbatim supporting sentence (sidecar; from EvidenceSpan)
    span_matched: bool        # EvidenceSpan.matched — precision-1.0 fabrication check
    status: str               # "settled" | "uncertain"      ← the gate's verdict
    flags: list[str]          # ["stale_currency","off_domain","unmatched_span","coverage_gap"]
    year: int | None          # freshest cited source year (for the date-stamp)

@dataclass
class DecisionCard:
    bottom_line: list[ReviewedClaim]     # settled, decision-changing, span-matched
    decision_furniture: list[ReviewedClaim]  # thresholds/comparators/exclusions/effect sizes
    uncertainties: list[ReviewedClaim]   # status=="uncertain" → the amber lane
    conflicts: list[str]                 # sources disagree (already stated inline by WOVEN_SYSTEM)
    prose: str                           # the full answer, verbatim (expandable)
```

**Step 1 — Extract management claims.** Reuse `evidence_spans.extract_and_verify` (already the
"evidential claim" extractor: number/threshold/comparator/recommendation/trial). Add a lightweight
**deterministic category tag** on top of each extracted claim via keyword/regex cues
(`indication|contraindication|first-line|superior to|approved|FDA|trial name`), so no new LLM call.
A claim that is not management-relevant (`category=="other"`) stays in prose, out of the card.

**Step 2 — Require a matching span.** `EvidenceSpan.matched` already gives this. `matched=False`
→ `flags += ["unmatched_span"]` → `status="uncertain"`. This is the precision-1.0 fabrication gate,
free.

**Step 3 — Deterministic checks (model-free):**
- **Freshness.** `_currency_language(claim)` regex for `latest|current|now standard|approved|newest`.
  If present AND the freshest cited source `year` is older than `CURRENCY_MAX_AGE` (default 3 y from a
  passed `now_year`, never `Date.now()` in a determinism-sensitive path) → `flags += ["stale_currency"]`.
  Year source: `[L#]`/`[D#]` records carry `year`; `[n]` textbook uses the book's publication year
  (static map, Youmans 8e = 2022).
- **Coverage.** Split the question into limbs (deterministic: split on `and|vs|versus|,` + `?`), and
  assert each limb's head noun appears in the answer. A missing limb → `flags += ["coverage_gap"]` on
  the card (not on a claim) → surfaced under uncertainties as "did not address: <limb>".
  *(Known ceiling: regex limb-splitting is the lowest-confidence of the three checks — it will miss
  implicit limbs and over-split lists. It is display-only (surfaces a note, never withholds a claim),
  so a false split is low-stakes; upgrade path is a one-shot LLM limb extraction if the fixture set
  shows it matters. Ponytail: ship the regex, measure, upgrade only if SP3 says so.)*
- **Same-domain.** Reuse the §2.1 domain router (`corpus.py` / the `_offdomain` machinery): if a cited
  `[D#]`/`[L#]` record's subspecialty ≠ the question's routed subspecialty → `flags += ["off_domain"]`
  on that claim. Guards the documented crowding failure (a stroke guideline answering a TBI question).

**Step 4 — Soften / withhold.** Any claim with a non-empty `flags` → `status="uncertain"`, routed to
`uncertainties`, rendered amber ("uncertain — verify current guidance: <reason>"). A settled claim is
one that is span-matched AND flag-free. **Nothing is deleted from prose** — the full answer stays
expandable; the card is a *lens* over it, not a rewrite. (This respects Sentinel-21: no claim is dropped.)

**Step 5 — Assemble.** `bottom_line` = settled management claims, deduped, in answer order.
`decision_furniture` = the threshold/comparator/exclusion/effect-size claims the furniture prompt
already elicits. `uncertainties` = the amber lane. `conflicts` = disagreements (the woven prompt
already makes the model state these; extract the "disagree"/"contradict" sentences).

**Failure-safety:** the whole function is wrapped so any exception → `DecisionCard(prose=answer,
bottom_line=[], …)` — i.e. the reader still gets the full answer, just without the card overlay.

**Runnable check (ponytail):** one `test_claim_review.py` with asserts — a stale-currency claim on a
2016 source flags; a span-unmatched claim goes uncertain; a clean claim stays settled; an empty/garbage
answer returns a prose-only card without raising.

## 6. Transport (Sub-project 0 — ships first, independently)

Additive fields only; no behavior change; every consumer degrades if absent.

- `server.py`: add `evidence_spans` and `decision_card` to the `/api/ask` response dict
  (`server.py:555`) and a new `evidence` stream event in `_serialize_ask_event` (`server.py:433`).
- `_citation_dict` (`server.py:332`): add `printed_page` (folio) and `page_image_url` (reuse the
  figure/page-image path) and the chunk `text` (the click-to-quote premise). Keep `page` for
  back-compat; the UI prefers `printed_page`.
- Regenerate the generated TS types and keep the existing pytest drift-guard green (per the
  operative-briefing bundle pattern).

## 7. Render (Sub-project 2 — web `AnswerView.tsx`, + `render_md.py` for CLI/exports)

Progressive disclosure, top to bottom:

```
┌─ DECISION CARD ─────────────────────────────────────────────┐
│ BOTTOM LINE                                                  │
│   • <settled claim>            [2] [L3]      (2023)          │
│ WHAT CHANGES THE DECISION                                    │
│   threshold  · comparator · who's excluded · effect size    │
│ ⚠ UNCERTAIN — verify current guidance                        │
│   • <claim>   reason: source is 2016, question asks "latest" │
│   did not address: <limb>                                    │
├─ full answer (expandable) ──────────────────────────────────┤
│   …prose with [n] markers; click [2] → quoted span + page   │
│   image of the folio (§3.4)…                                │
└─────────────────────────────────────────────────────────────┘
```

- Amber uses the `-ink` token on light surfaces per the web contrast model (`--color-amber-ink`),
  never `text-amber`.
- Click `[n]` → drawer/popover with the `EvidenceSpan.quote` and the rendered page image
  (`page_image_url`). "Show me the page" is one hop from "trust me."
- CLI/`render_md.py`: the same card as a leading Markdown block; the folio (not PDF page) is what
  opens (already done for `answers.md` in `f666d0c` — reuse it).

## 8. Validation & gating (Sub-project 3 — what lets the flags flip to default)

Deterministic assertions land as pytest under `evaluation/assertions/` (CI is pytest-only, so they
are free gates):

- **D14** every `[n]/[L#]/[D#]` in the card resolves to a real premise **and** a page image on disk.
- **D15** the verbatim quote string-matches its cited chunk (`partial_ratio ≥ 95`) on ≥98% of
  evidential claims (already in `evidence_spans`; assert it end-to-end through the card).
- **NEW D-gate** freshness/coverage/same-domain precision on a small labeled fixture set
  (`evaluation/claim-review/labeled.jsonl`): the gate must not soften a claim a human marked current
  (precision floor pre-registered — the repo already learned an under-precise gate is worse than none,
  the ⚠ badge at 0.24).
- **Prose non-inferiority** D19–D22 already specified in `FIX_PLAN` §6.5 apply to the card overlay
  (the card must not rewrite prose): assert `card.prose == answer`.

Human instruments (§6.3 Instrument B — the 20-item citation-opening audit) are the surgeon's ~15 min
and gate the default flip. Not my code; my code produces the artifact he audits.

## 9. Decomposition & sequencing (each sub-project → its own plan → implementation)

```
SP0  Transport      serialize evidence_spans + decision_card + folio/page-image/text;
                    regen TS types.  Additive, no behavior change. Ships alone.  ← first
SP1  The gate       claim_review.py + wire in qa._answer_question_woven behind DECISION_CARD.
                    Deterministic; failure-safe; reuses built machinery.
SP2  The render     AnswerView.tsx Decision Card + click-to-quote→page; render_md.py card block.
SP3  Validation     D14/D15/D-gate assertions + labeled fixture; hand the audit artifact to §6.
```

SP0 is the smallest shippable unit and unblocks a visible click-to-quote immediately even before the
gate exists. SP1 is the genuinely-new logic. SP2 makes it a product. SP3 is what earns the default flip.

## 10. File manifest

```
neuro_caseboard/claim_review.py                         # SP1 — the gate (new)
tests/test_claim_review.py                              # SP1 — runnable check (new)
neuro_caseboard/qa.py                                   # SP1 — one call site + QAResult field
api/server.py                                           # SP0 — serialize spans+card+folio/page/text
web/src/components/ask/AnswerView.tsx                   # SP2 — Decision Card render
web/src/lib/api.ts  (+ generated types)                 # SP0/SP2 — types
neuro_caseboard/render_md.py                            # SP2 — CLI/export card block
evaluation/assertions/test_citation_invariants.py       # SP3 — D14/D15 through the card
evaluation/assertions/test_claim_review_gate.py         # SP3 — freshness/coverage/same-domain precision (new)
evaluation/claim-review/labeled.jsonl                   # SP3 — labeled fixture (new)
```

## 11. Explicit non-goals

- Not flipping any existing flag to default (that is §6's decision, on evidence).
- Not adding a second live LLM judge pass (Approach C rejected).
- Not rewriting prose to satisfy the card (quotes stay in the sidecar; prose is verbatim).
- Not building the full §6 human-grading harness here (SP3 produces the artifact; the surgeon grades).
