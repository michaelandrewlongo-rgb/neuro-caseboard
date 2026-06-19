# Build Source Attribution — Cross-Domain Leakage Regression Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee a Build dossier is titled from the procedure prompt and never presents an off-target (e.g. spine) textbook as a representative citation for a cranial case — and pin it with a regression test for cross-domain source leakage (BACKLOG P1 #1).

**Architecture:** The leakage *fix* already lives in the engine and is merged on master: `pipeline._sources_from_audited` exports **only** `caseprep.audit.card_auditor.accepted_papers(card)` (= `card.papers` minus `contradicting_paper_ids`); `compile._compile` routes `rejected_papers(card)` into a dedicated **"Rejected Sources (off-target)"** appendix and never into the "Evidence Sources" list; and `compile_dossier` sets `title = f"Case Board — {topic}"`. The missing requirement is (4): a **build-dossier-level regression test** that proves an off-target paper riding on an *accepted/supported* card stays out of every representative citation and the title, while remaining in the rejected-sources appendix for provenance completeness. This plan adds that test as the loop harness file. If any assertion fails on first run, it has revealed a residual leak path → Task 2 (contingent) closes it.

**Tech Stack:** Python 3.10+, pytest, `caseprep.audit.card_auditor` (`AuditedManifest`, `AuditedCard`, `accepted_papers`/`rejected_papers`), `neuro_caseboard.compile.compile_dossier`, `neuro_caseboard.pipeline._sources_from_audited`. Hermetic — no corpus / retriever / LLM / network.

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_build_source_attribution.py`. Full suite is ~17min on WSL2 — keep the inner loop scoped to this file; CI runs the full suite.
- Engine behavior change is OUT OF SCOPE unless a Task-1 assertion fails. Do NOT modify `neuro_caseboard/` or vendored `caseprep/` unless a test proves a live leak; this is primarily a regression-pinning deliverable.
- Test must be hermetic: construct an in-memory `AuditedManifest`; never touch the corpus, retriever, LLM, or network. No new dependencies.
- The off-target source MAY (and must) appear in the dedicated "Rejected Sources (off-target)" appendix entry — that is correct provenance, not leakage. Assertions must exclude that one appendix entry when scanning for leaks.
- Exact model facts (verified): `AppendixEntry(heading: str, items: list[str], sources: list[str])`; `Dossier(title, summary, sections, appendix)`; `Appendix.entries`; `Section.claims[].text`, `Section.figures[].citation`. `compile_dossier(audited_manifest, *, topic, evidence=..., card_evidence=..., page_texts=...)`.

---

## Tasks (project-loop step cursor)

The loop's `step_cursor` indexes these top-level items only.

- [x] Task 1: Cross-domain source-leakage regression test (`tests/test_build_source_attribution.py`)
- [x] Task 2 (CONTINGENT — TRIGGERED): fixed `compile._compile` rejected-paper loop var `title`→`rtitle` (dossier-title clobber). Both delivered in commit 892d8e7.

---

### Task 1: Cross-domain source-leakage regression test

**Files:**
- Create (Test): `tests/test_build_source_attribution.py`

**Interfaces:**
- Consumes: `caseprep.audit.card_auditor.{AuditedManifest, AuditedCard}`; `neuro_caseboard.compile.compile_dossier`; `neuro_caseboard.pipeline._sources_from_audited`.
- Produces: nothing (test-only).

**Verified facts (hold while writing the test):**
- `_sources_from_audited(manifest)` returns `list[EvidenceRecord]` built from `accepted_papers` only; it is the exact build-path evidence builder, so using it (rather than hand-rolled evidence) gives the test teeth against the real export path.
- `accepted_papers(card)` = `card.papers` minus papers whose id ∈ `card.contradicting_paper_ids`; `rejected_papers(card)` = the complement. Paper id is read from the paper dict's `id`.
- A `supported` card may still carry an off-target paper in `contradicting_paper_ids` — that is the precise leak case (the card is not quarantined, so a naive exporter would still ship the off-target source).
- `compile_dossier` build path uses `corpus_inline=False`, so off-target papers cannot become inline `[n]` claim citations; the representative provenance surface is the "Evidence Sources" appendix + any figure `citation`.

**Step 1: Write the failing test**

Create `tests/test_build_source_attribution.py`:

```python
"""Regression: cross-domain source leakage in the Build dossier (BACKLOG P1 #1).

A cranial case must never be titled with, or cite, an off-target (e.g. spine) textbook — even when
the off-target paper rides on a card that was itself accepted/supported. The Auditor flags such
papers via ``contradicting_paper_ids``; they must stay out of every representative citation and the
title, and appear only in the dedicated "Rejected Sources (off-target)" appendix.

Hermetic: builds an AuditedManifest in-memory and compiles it; no corpus / retriever / LLM / net.
This test has teeth — it fails against a pre-fix exporter that shipped every paper regardless of the
Auditor's ``contradicting_paper_ids`` flag.
"""
from caseprep.audit.card_auditor import AuditedCard, AuditedManifest

from neuro_caseboard.compile import compile_dossier
from neuro_caseboard.pipeline import _sources_from_audited

CRANIAL_TOPIC = "pterional craniotomy for MCA aneurysm clipping"
ONTARGET = {"id": "p_on", "title": "Lawton - Seven Aneurysms", "source": "corpus",
            "text_snippet": "pterional approach to the MCA bifurcation aneurysm"}
OFFTARGET_SPINE = {"id": "p_off", "title": "Vaccaro - Spine Surgery", "source": "corpus",
                   "text_snippet": "posterior lumbar interbody fusion hardware"}


def _manifest() -> AuditedManifest:
    # SUPPORTED cranial card carrying BOTH an on-target paper and an off-target spine paper; the
    # spine paper is flagged contradicting. The card is NOT quarantined (audit_status="supported"),
    # which is exactly the case where an unfiltered exporter leaks the off-target source.
    card = AuditedCard(
        question="Which arteries are at risk during the pterional approach?",
        why_it_matters="Defines the dissection corridor and the rescue plan.",
        target_file="anatomy", section_key="arteries_at_risk",
        answerability="needs_patient_fact", audit_status="supported",
        papers=[dict(ONTARGET), dict(OFFTARGET_SPINE)],
        contradicting_paper_ids=["p_off"],
    )
    return AuditedManifest(procedure_family=CRANIAL_TOPIC, cards=[card])


def _representative_strings(dossier) -> list[str]:
    """Every provenance-bearing string EXCEPT the dedicated Rejected-Sources appendix (which is
    allowed — required — to name the off-target paper)."""
    out: list[str] = []
    for s in dossier.sections:
        out += [cl.text for cl in s.claims]
        out += [(fig.citation or "") for fig in s.figures]
    for e in dossier.appendix.entries:
        if e.heading.startswith("Rejected Sources"):
            continue
        out += list(e.sources)
    return out


def _build():
    m = _manifest()
    return compile_dossier(m, topic=CRANIAL_TOPIC, evidence=_sources_from_audited(m))


def test_title_is_derived_from_procedure_prompt_not_a_book():
    d = _build()
    assert d.title == f"Case Board - {CRANIAL_TOPIC}".replace("Case Board -", "Case Board —") \
        or d.title == f"Case Board — {CRANIAL_TOPIC}"
    assert "Vaccaro" not in d.title and "Spine" not in d.title


def test_offtarget_source_never_appears_as_a_representative_citation():
    d = _build()
    leaked = [s for s in _representative_strings(d) if "Vaccaro" in s or "Spine Surgery" in s]
    assert leaked == [], f"off-target spine source leaked into representative provenance: {leaked}"


def test_accepted_ontarget_source_is_still_exported():
    # Sanity: the accepted-only filter removes the off-target paper WITHOUT nuking the real source.
    d = _build()
    evidence = [e for e in d.appendix.entries if e.heading == "Evidence Sources"]
    assert evidence, "expected an 'Evidence Sources' appendix entry"
    assert any("Lawton" in s for s in evidence[0].sources)


def test_offtarget_source_is_preserved_in_the_rejected_appendix():
    # Provenance completeness: the off-target paper is disclosed, just never as a citation.
    d = _build()
    rejected = [e for e in d.appendix.entries if e.heading.startswith("Rejected Sources")]
    assert rejected, "expected a 'Rejected Sources (off-target)' appendix entry"
    assert any("Vaccaro" in s for s in rejected[0].sources)
```

> Title-assert note: `compile_dossier` builds the title as `f"Case Board — {topic}"` (em dash). The implementer must confirm the exact glyph by reading `neuro_caseboard/compile.py:compile_dossier` and assert the literal it produces — simplify the `test_title_*` assertion to the single exact string the code emits (drop the defensive `or`). The load-bearing assertion is that no book name appears in the title.

**Step 2: Run the test to verify the starting state**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_build_source_attribution.py`
Expected: All tests PASS against current master (the accepted-only fix is already merged). This is the regression-lock outcome. **If any test FAILS**, it has found a live cross-domain leak — capture the failing assertion and proceed to Task 2.

> Teeth check (do NOT commit this): temporarily edit `pipeline._sources_from_audited` to iterate `c.papers` instead of `accepted_papers(c)`, re-run — `test_offtarget_source_never_appears_as_a_representative_citation` MUST fail. Revert immediately. This proves the regression test guards the real fix. (Optional but recommended; the loop's evidence gate does not require it.)

**Step 3: Finalize the title assertion**

Read `neuro_caseboard/compile.py` `compile_dossier`, confirm the exact title string, and replace the `test_title_*` body with a single exact-equality assertion plus the no-book-name assertions. Re-run the harness; expect 4 passed.

**Step 4: Commit**

```bash
git add tests/test_build_source_attribution.py
git commit -m "loop step 0: regression test for cross-domain Build source leakage (P1 #1)"
```

---

### Task 2 (CONTINGENT): close the residual leak path

**Only execute if a Task-1 assertion failed against current master.** If Task 1 passed, mark this task `[x]` as not-needed with a one-line note and proceed to PR.

**Files (likely candidates, confirm from the failing assertion):**
- Modify: `neuro_caseboard/pipeline.py` (`_sources_from_audited`) or `neuro_caseboard/compile.py` (`_compile` citation assembly), depending on which surface leaked.

**Step 1:** Use the failing assertion's `leaked` list to identify the surface (Evidence Sources vs. figure citation vs. title).

**Step 2:** Apply the minimal filter so the off-target/rejected source is excluded from that surface while remaining in the Rejected-Sources appendix — mirror the existing `accepted_papers` pattern; do not invent a new policy.

**Step 3:** Re-run the harness; expect all tests green. Confirm no other `tests/` file regresses by running the affected module(s).

**Step 4: Commit**

```bash
git add -A
git commit -m "loop step 1: exclude off-target source from <surface> representative citation"
```

---

## Self-Review

**1. Spec coverage:** (1) title-from-prompt → `test_title_is_derived_from_procedure_prompt_not_a_book`. (2) accepted-only header provenance → `test_accepted_ontarget_source_is_still_exported` + the leakage test using `_sources_from_audited`. (3) rejected/quarantined excluded from representative citations → `test_offtarget_source_never_appears_as_a_representative_citation`. (4) regression test for cross-domain leakage → the whole file (with teeth check). ✔
**2. Placeholder scan:** All steps contain runnable code/commands and exact expected output; Task 2 is explicitly contingent, not a TODO. ✔
**3. Type consistency:** `AppendixEntry.sources`/`.heading`, `Dossier.appendix.entries`, `Section.claims[].text`, `Section.figures[].citation`, `compile_dossier(..., topic=, evidence=)`, `_sources_from_audited(manifest)` all verified against source. ✔
