"""Domain-contradiction auditing (P2 #8).

`_audit_card` must default to ``needs_review`` rather than falsely flagging an
in-domain paper as ``off_target`` just because it mentions one stray
contradiction term (e.g. a strongly-vascular abstract that names "glioma" in a
differential). Genuinely off-domain papers must still be quarantined. Also
covers the ``1 paper`` (not ``1 papers``) pluralization of the count-bearing
``audit_reason`` strings.

Hermetic: calls ``_audit_card`` directly with SimpleNamespace cards and dict
papers; no corpus / network.
"""

from __future__ import annotations

from types import SimpleNamespace

from caseprep.audit.card_auditor import _audit_card, _plural, accepted_papers


def _card(*, question: str, why: str, papers: list[dict]) -> SimpleNamespace:
    """An EnrichedCard stand-in carrying exactly the attrs `_audit_card` reads."""
    return SimpleNamespace(
        question=question,
        why_it_matters=why,
        target_file="anatomy.md",
        section_key="vascular",
        compiler_slot="approach",
        answerability="answerable",
        papers=papers,
        confidence=None,
        enrichment_status="success",
    )


VASCULAR_TOPIC = "ruptured anterior communicating artery aneurysm clipping"
VASCULAR_QUESTION = "What is the optimal approach to clipping a ruptured aneurysm?"
VASCULAR_WHY = "Clipping vs endovascular coiling changes the operative plan."


def test_in_domain_paper_with_stray_contradiction_term_is_not_off_target():
    """FALSE-POSITIVE FIX. A strongly-vascular paper that also says "glioma"
    once is detected as ``paper_domain == vascular`` (domain_match True), so the
    stray contradiction term must NOT make it off_target.

    Pre-fix the decision branch was ``if contradictions:`` (checked before the
    positive domain match), so this paper WAS flagged off_target and this assert
    FAILED — that is what the threshold change (``and not domain_match``) fixes.
    """
    paper = {
        "id": "P1",
        "title": "Endovascular coiling and microsurgical clipping of a ruptured ACoA aneurysm",
        "text_snippet": (
            "Thrombectomy was avoided; vasospasm was managed medically. "
            "Differential considered a glioma but imaging confirmed aneurysm."
        ),
    }
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[paper])
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status != "off_target", audited.audit_reason
    # And it should be positively classified, not merely spared:
    assert audited.audit_status == "supported"


def test_genuinely_off_domain_paper_still_off_target():
    """NON-REGRESSION. A clearly-tumor paper (no vascular terms) for a vascular
    case: paper_domain=tumor_craniotomy, domain_match False, contradiction terms
    present → must still be quarantined as off_target."""
    paper = {
        "id": "T1",
        "title": "Awake craniotomy for glioma resection",
        "text_snippet": "Gross total resection (GTR) achieved with motor mapping of eloquent cortex.",
    }
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[paper])
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status == "off_target", audited.audit_reason
    assert audited.contradicting_paper_ids == ["T1"]


def test_audit_reason_pluralization_one_supported_paper():
    """Exactly 1 supported paper → ``1 paper`` (not the old ``1 papers``)."""
    paper = {
        "id": "V1",
        "title": "Stent retriever thrombectomy for large vessel occlusion",
        "text_snippet": "Aneurysm clipping series; TICI 2b reperfusion after coiling.",
    }
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[paper])
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status == "supported", audited.audit_reason
    assert "1 paper " in audited.audit_reason
    assert "1 papers" not in audited.audit_reason


def test_audit_reason_pluralization_two_supported_papers():
    """2 supported papers → ``2 papers``."""
    papers = [
        {
            "id": "V1",
            "title": "Stent retriever thrombectomy for large vessel occlusion",
            "text_snippet": "Aneurysm clipping series; TICI 2b reperfusion.",
        },
        {
            "id": "V2",
            "title": "Endovascular coiling vs clipping of ruptured aneurysm",
            "text_snippet": "Embolization and flow diversion outcomes; NIHSS at discharge.",
        },
    ]
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=papers)
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status == "supported", audited.audit_reason
    assert "2 papers" in audited.audit_reason


def test_plural_helper():
    assert _plural(1, "paper") == "1 paper"
    assert _plural(2, "paper") == "2 papers"
    assert _plural(0, "paper") == "0 papers"


# ── PR #63 review fixes (word-boundary domain matching) ──────────────────────

NOISE_MENINGIOMA_PAPER = {
    "id": "M1",
    "title": "Clinical aspects of meningioma.",
    "text_snippet": "Surgical resection of a meningioma.",
}


def test_off_domain_meningioma_with_substring_noise_stays_quarantined():
    """MUST (PR #63 review). The clinical-safety regression guard.

    An off-domain meningioma paper whose only "vascular" signal is substring
    NOISE — ``clinical`` and ``surgical`` both CONTAIN "ica", and ``aspects`` is
    the plain English word (intended as the ASPECTS stroke score) — must NOT be
    mis-detected as vascular and must stay quarantined.

    Pre-fix (unbounded ``term in lower`` substring matching + ``"aspects"`` still
    in the vascular lexicon) this paper scored vascular=2 (ica-in-clinical/surgical
    + aspects) > tumor=1 (meningioma), so ``_detect_domain`` returned "vascular" →
    ``domain_match`` True → its "meningioma" contradiction was NOT quarantined → it
    escaped into ``needs_review`` (and ``accepted_papers``, i.e. citable in the
    primary dossier). Word-boundary matching makes vascular=0, and dropping the
    ``"aspects"`` noise term keeps it so → tumor=1 → ``off_target`` again. This test
    FAILS on the pre-fix code (it is classified ``needs_review``) and PASSES after.
    """
    card = _card(
        question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[NOISE_MENINGIOMA_PAPER]
    )
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    # It must be quarantined, never spared into a citable status.
    assert audited.audit_status == "off_target", audited.audit_reason
    assert audited.audit_status != "supported"
    # The paper id is recorded as contradicting and is NOT in the accepted set.
    assert "M1" in audited.contradicting_paper_ids
    assert "M1" not in [p["id"] for p in accepted_papers(audited)]
    assert accepted_papers(audited) == []


def test_off_domain_plural_only_contradiction_still_quarantined():
    """REVIEW FOLLOW-UP (PR #63). Word-boundary matching must still catch REGULAR
    ``-s`` plurals (the ``s?`` in ``_has_term``), else an off-domain tumor paper
    that names ONLY plural forms ("meningiomas", "gliomas") would escape off_target
    into a citable status — the same harm class as the noise-term MUST.

    Fails on the bare-``\\b`` matching (no contradiction term matches the plurals →
    paper falls through to ``needs_review`` and is citable); passes with ``s?``
    (paper_domain=tumor via the plurals, contradiction present → ``off_target``).
    """
    paper = {
        "id": "M2",
        "title": "Surgical management of multiple meningiomas",
        "text_snippet": "A series of resected meningiomas and gliomas; recurrence was analyzed.",
    }
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[paper])
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status == "off_target", audited.audit_reason
    assert "M2" in audited.contradicting_paper_ids
    assert "M2" not in [p["id"] for p in accepted_papers(audited)]


def test_off_target_reason_pluralization_one_paper():
    """SHOULD (PR #63 review). The OFF_TARGET reason string also pluralizes:
    exactly 1 off_target paper reads ``1 paper contradict`` (not ``1 papers``)."""
    paper = {
        "id": "T2",
        "title": "Awake craniotomy for glioma resection",
        "text_snippet": "Gross total resection (GTR) achieved with motor mapping of eloquent cortex.",
    }
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[paper])
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status == "off_target", audited.audit_reason
    assert "1 paper " in audited.audit_reason
    assert "1 papers" not in audited.audit_reason


def test_paper_domain_none_with_contradiction_only_is_off_target():
    """SHOULD (PR #63 review). A paper with NO positive lexicon signal
    (``paper_domain`` is None → ``domain_match`` False) but a single contradiction
    token ("acdf") on a vascular case must still be quarantined as off_target."""
    paper = {
        "id": "A1",
        "title": "A case report",
        "text_snippet": "acdf",
    }
    card = _card(question=VASCULAR_QUESTION, why=VASCULAR_WHY, papers=[paper])
    audited = _audit_card(card, topic=VASCULAR_TOPIC)
    assert audited.audit_status == "off_target", audited.audit_reason
    assert "A1" in audited.contradicting_paper_ids
