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
        target_file="anatomy", section_key="arteries_at_risk", compiler_slot="",
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
    assert d.title == f"Case Board — {CRANIAL_TOPIC}"
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
