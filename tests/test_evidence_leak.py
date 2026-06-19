"""Evidence-leakage guard: only auditor-accepted papers may become citations / sources.

Background: the Auditor already partitions each card's retrieved papers into
``supporting_paper_ids`` and ``contradicting_paper_ids``. A card that has *both* a
supporting paper and a contradicting (off-target) paper is still marked ``supported``
(supported wins), so it stays in the primary dossier — it is NOT quarantined. The bug:
the consumers (``_sources_from_audited`` and the inline ``[n]`` builder) exported *every*
paper on the card, so the off-target paper leaked into the Evidence Sources and could even
be the target of an inline citation — "an off-target source despite 0 quarantined cards".

``accepted_papers(card)`` / ``rejected_papers(card)`` make the auditor's own partition the
single gate: only accepted papers may be cited / listed; rejected papers go to a separate
appendix section.
"""

from __future__ import annotations

import re

import pytest

from caseprep.core.contracts import EvidenceRecord
from caseprep.audit.card_auditor import (
    AuditedCard, AuditedManifest, accepted_papers, rejected_papers,
)
from neuro_caseboard.case_context import CaseContext

_OFF = "Convexity meningioma gross total resection series"     # off-target for a vascular case
_CORPUS = re.compile(r"(?<!L)\[(\d+)\]")                        # [3] but not [L3]


def _vascular_case():
    return CaseContext.from_dict({
        "laterality": "right", "level": "MCA", "pathology": "ruptured MCA aneurysm",
        "procedure": "microsurgical clipping", "surgical_goal": "aneurysm clip ligation",
        "presentation": "right MCA aneurysm for clipping",
    })


class _OffTargetRetriever:
    """For every card: one off-target meningioma paper FIRST, then two on-domain vascular
    papers. The real Auditor must put the meningioma in ``contradicting_paper_ids`` for a
    vascular case (vascular contradiction terms: meningioma / gross total resection)."""

    def retrieve(self, query, *, top_n=5, subdomain=None):
        recs = [
            EvidenceRecord(id="off1", source="corpus", title=_OFF,
                           text="meningioma gross total resection awake craniotomy convexity",
                           metadata={"citation": _OFF}),
            EvidenceRecord(id="vas1", source="corpus",
                           title="Microsurgical clipping of ruptured MCA aneurysm",
                           text="aneurysm clipping mca ica subarachnoid hemorrhage",
                           metadata={"citation": "Microsurgical clipping of ruptured MCA aneurysm"}),
            EvidenceRecord(id="vas2", source="corpus",
                           title="Coiling versus clipping for cerebral aneurysm",
                           text="aneurysm coiling clipping basilar endovascular",
                           metadata={"citation": "Coiling versus clipping for cerebral aneurysm"}),
        ]
        return recs[:top_n]


def _sources(dossier):
    for e in dossier.appendix.entries:
        if e.heading == "Evidence Sources":
            return list(e.sources)
    return []


def _rejected_appendix(dossier):
    titles = []
    for e in dossier.appendix.entries:
        if "rejected" in e.heading.lower() or "off-target" in e.heading.lower():
            titles += list(e.sources) + list(e.items)
    return titles


# ── 1. unit: the partition helpers project the auditor's id lists onto paper dicts ──────

def test_accepted_papers_excludes_contradicting_and_keeps_the_rest():
    card = AuditedCard(
        question="q", why_it_matters="w", target_file="08-surgical-technique.md",
        section_key="key_steps", compiler_slot="Key Steps", answerability="needs_patient_fact",
        audit_status="supported",
        supporting_paper_ids=["vas1"], contradicting_paper_ids=["off1"],
        papers=[{"id": "off1", "title": _OFF},
                {"id": "vas1", "title": "Clipping technique"},
                {"id": "mid1", "title": "Uncertain middle paper"}],   # needs_review (neither list)
    )
    acc_ids = {p["id"] for p in accepted_papers(card)}
    rej_ids = {p["id"] for p in rejected_papers(card)}
    assert rej_ids == {"off1"}                       # only the contradicting paper is rejected
    assert acc_ids == {"vas1", "mid1"}               # supporting + neither survive
    assert "off1" not in acc_ids                     # the tempting wrong one is gone


def test_helpers_are_empty_safe_on_cards_without_papers():
    card = AuditedCard(question="q", why_it_matters="w", target_file="x", section_key="k",
                       compiler_slot="s", answerability="a")
    assert accepted_papers(card) == [] and rejected_papers(card) == []


# ── 2. compile consumer: inline [n] / Evidence Sources gate on the accepted set ─────────

def test_compile_case_inline_citations_never_point_at_rejected_paper():
    from neuro_caseboard.compile import compile_case_dossier
    # A supported, corpus-eligible card whose FIRST paper is the off-target one (so the old
    # "first papers" rule would cite it as [1]).
    card = AuditedCard(
        question="Clip the aneurysm neck after proximal control of the parent vessel",
        why_it_matters="Proximal control prevents catastrophic intraoperative rupture",
        target_file="08-surgical-technique.md", section_key="key_steps",
        compiler_slot="Key Steps", answerability="needs_patient_fact",
        audit_status="supported",
        supporting_paper_ids=["vas1"], contradicting_paper_ids=["off1"],
        papers=[{"id": "off1", "title": _OFF},
                {"id": "vas1", "title": "Microsurgical clipping technique for MCA aneurysm"}],
    )
    manifest = AuditedManifest(procedure_family="case", cards=[card])
    d = compile_case_dossier(manifest, case=_vascular_case())

    sources = _sources(d)
    assert "Microsurgical clipping technique for MCA aneurysm" in sources   # accepted preserved
    assert _OFF not in sources                                              # rejected excluded
    # the claim still carries an inline [n] (grounded), and every [n] resolves to a non-rejected
    # source (sources list defines the numbering, and _OFF is no longer in it).
    marks = [int(m) for s in d.sections for cl in s.claims for m in _CORPUS.findall(cl.text)]
    assert marks, "the supported claim should still carry an inline corpus citation"
    assert max(marks) <= len(sources)
    assert _OFF in _rejected_appendix(d)                                    # surfaced separately


# ── 3/4. activation on the REAL auditor path (enrich -> audit -> compile) ────────────────

def test_sources_from_audited_excludes_rejected_via_real_auditor():
    from neuro_caseboard.case_author import deterministic_case_manifest
    from neuro_caseboard.guard import prune_offtarget
    from caseprep.enrichment.corpus_enricher import enrich_manifest
    from caseprep.audit.card_auditor import audit_manifest
    from neuro_caseboard.pipeline import _sources_from_audited

    case = _vascular_case()
    manifest = prune_offtarget(deterministic_case_manifest(case), case.to_topic())
    enriched = enrich_manifest(manifest, topic=case.to_topic(),
                               retriever=_OffTargetRetriever(), top_n=3)
    audited = audit_manifest(enriched, topic=case.to_topic())

    # sanity: the real auditor genuinely flagged the off-target paper as contradicting on a
    # card that nonetheless stayed primary (not quarantined) — the exact reported scenario.
    leaked_card = next(c for c in audited.cards if "off1" in c.contradicting_paper_ids
                       and c.audit_status in ("supported", "needs_review"))
    assert leaked_card is not None

    titles = [e.title for e in _sources_from_audited(audited)]
    assert _OFF not in titles                                   # off-target no longer exported
    assert any("clipping" in t.lower() for t in titles)        # the on-domain sources remain


def test_case_dossier_quarantines_offtarget_source_end_to_end():
    from neuro_caseboard.pipeline import build_case_dossier
    d = build_case_dossier(_vascular_case(), enrich=True, retriever=_OffTargetRetriever(),
                           use_llm=False, literature=False)
    sources = _sources(d)
    assert sources, "the vascular case should still carry on-domain corpus sources"
    assert _OFF not in sources                                  # no off-target in Evidence Sources
    for s in d.sections:                                        # nor cited inline anywhere
        for cl in s.claims:
            for n in _CORPUS.findall(cl.text):
                assert sources[int(n) - 1] != _OFF
    assert _OFF in _rejected_appendix(d)                        # listed in the rejected appendix
