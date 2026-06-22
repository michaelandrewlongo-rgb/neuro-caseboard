"""Trust contract for quarantined (off-target) cards in the Dossier.

Off-target retrievals must surface as badged ``status="quarantine"`` claims INSIDE their
section's claim list — never silently dropped, never double-listed in the appendix — and the
rendered quarantine-claim count must equal the ``EvidenceSummary.quarantined`` gauge.
"""

import pytest

from neuro_caseboard.compile import compile_dossier
from neuro_caseboard.dedup import dedup_sections
from neuro_caseboard.model import Claim, Section
import tests.fixtures as fx


@pytest.fixture(params=fx.ALL_TOPICS)
def dossier(request):
    f = fx.build(request.param)
    return compile_dossier(f.manifest, topic=f.topic, evidence=f.evidence,
                           card_evidence=f.card_evidence, page_texts=f.page_texts)


def test_quarantine_claim_count_equals_gauge(dossier):
    quar = [c for s in dossier.sections for c in s.claims if c.status == "quarantine"]
    # the gauge count must equal the rendered count
    assert len(quar) == dossier.summary.quarantined
    # the fixtures plant exactly one off_target card per topic
    assert dossier.summary.quarantined == 1


def test_quarantine_claims_are_well_formed(dossier):
    quar = [c for s in dossier.sections for c in s.claims if c.status == "quarantine"]
    assert quar
    for c in quar:
        assert c.status == "quarantine"
        assert c.text.strip()


def test_no_appendix_double_listing_of_quarantine_claims(dossier):
    quar_texts = {c.text.strip().lower()
                  for s in dossier.sections for c in s.claims if c.status == "quarantine"}
    appendix_items = {i.strip().lower()
                      for e in dossier.appendix.entries for i in e.items}
    # Scan BOTH appendix axes (.items AND .sources): off-target content must not be re-listed
    # in the appendix either way, so a regression that moved it into `sources` is also caught.
    appendix_sources = {sr.strip().lower()
                        for e in dossier.appendix.entries for sr in e.sources}
    assert quar_texts
    assert not (quar_texts & appendix_items)
    assert not (quar_texts & appendix_sources)


# ── Task 2: dedup must keep quarantine claims verbatim and never let them suppress others ──
_TEXT = "Watertight dural closure with a fascial graft over a subgaleal drain"
_NEAR = "Watertight dural closure with a fascial graft over a subgaleal drain placed"


def _claim(text: str, status: str) -> Claim:
    # raw=text so dedup compares on this exact wording (Claim.dedup_text falls back to raw).
    return Claim(text=text, status=status, raw=text)


def test_dedup_never_removes_a_quarantine_claim():
    # An earlier primary claim is near-identical to a later quarantine claim. The quarantine
    # claim must survive verbatim — it is not a dedup victim.
    secs = [
        Section(heading="Operative Plan", claims=[_claim(_TEXT, "supported")]),
        Section(heading="Risk and Rescue", claims=[_claim(_NEAR, "quarantine")]),
    ]
    dedup_sections(secs)
    assert [c.text for c in secs[0].claims] == [_TEXT]
    surviving = secs[1].claims
    assert [c.status for c in surviving] == ["quarantine"]
    assert surviving[0].text == _NEAR  # kept verbatim


def test_dedup_quarantine_claim_does_not_suppress_a_primary_claim():
    # An earlier quarantine claim is near-identical to a later primary claim. The quarantine
    # claim must NOT enter the seen set, so the primary claim is not collapsed into a cross-ref.
    secs = [
        Section(heading="Anatomy at Risk", claims=[_claim(_TEXT, "quarantine")]),
        Section(heading="Operative Plan", claims=[_claim(_NEAR, "supported")]),
    ]
    dedup_sections(secs)
    assert [c.status for c in secs[0].claims] == ["quarantine"]
    assert [c.text for c in secs[1].claims] == [_NEAR]  # primary survived (not deduped)
    assert secs[1].cross_refs == []  # no "Also relevant — see …" cross-ref was injected
