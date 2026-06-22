"""Trust contract for quarantined (off-target) cards in the Dossier.

Off-target retrievals must surface as badged ``status="quarantine"`` claims INSIDE their
section's claim list — never silently dropped, never double-listed in the appendix — and the
rendered quarantine-claim count must equal the ``EvidenceSummary.quarantined`` gauge.
"""

import pytest

from neuro_caseboard.compile import compile_dossier
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
    assert quar_texts and not (quar_texts & appendix_items)
