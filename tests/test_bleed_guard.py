"""Ask-path anti-bleed guard: a cited claim that asserts a salient medical entity absent from its
cited premise is flagged needs-verification (the precision check that recall-based should_cite misses)."""

from neuro_caseboard.entailment import medical_entities, unsupported_entities
from neuro_caseboard.answer_verify import verify_answer, verification_notice


# A substantial glioma/insula premise that should_cite would ACCEPT on its own (rich recall +
# per-sentence precision) — so it is the bleed guard, not a recall failure, that flips the verdict.
_GLIOMA_PREMISE = ("The transsylvian approach opens the sylvian fissure to expose the insula and "
                   "reach an insular glioma; gross-total resection of the glioma is the operative goal.")


def test_cavernoma_bleed_flagged():
    claim = ("The transsylvian approach opens the sylvian fissure to reach the insular glioma, "
             "resecting the cavernoma [2].")
    v = verify_answer(claim, {"2": _GLIOMA_PREMISE})
    assert v.n_cited_claims == 1
    verdict = v.claims[0]
    assert verdict.supported is False
    assert verdict.bleed_terms == ["cavernoma"]   # glioma stays (it IS in the premise)
    assert v.n_unsupported == 1                    # counted once
    note = verification_notice(v)
    assert "cavernoma" in note
    assert "not found in the cited source" in note


def test_grounded_glioma_not_flagged():
    # Non-regression: the entity IS present in the cited premise -> no bleed, claim supported.
    claim = "Gross-total resection of the glioma is the goal [2]."
    v = verify_answer(claim, {"2": _GLIOMA_PREMISE})
    verdict = v.claims[0]
    assert verdict.bleed_terms == []
    assert verdict.supported is True
    assert v.n_unsupported == 0
    assert "not found in the cited source" not in verification_notice(v)


def test_no_medical_entity_claim_unchanged():
    # A grounded claim with no medical-entity tokens behaves exactly as before (no new flagging).
    claim = "The middle cerebral artery supplies the lateral cerebral cortex [2]."
    premise = "The middle cerebral artery supplies the lateral cerebral cortex and the insula."
    v = verify_answer(claim, {"2": premise})
    verdict = v.claims[0]
    assert verdict.bleed_terms == []
    assert verdict.supported is True
    assert v.n_unsupported == 0
    assert verification_notice(v) == ""


def test_medical_entities_extracts_entity_tokens_only():
    ents = medical_entities("A meningioma resected via craniotomy in the patient at the centre.")
    assert ents == {"meningioma", "craniotomy"}


def test_unsupported_entities_empty_when_all_present():
    claim = "Resect the meningioma during the craniotomy."
    premise = "A convexity meningioma is removed through a standard craniotomy and dural closure."
    assert unsupported_entities(claim, premise) == set()


def test_diagnosis_word_not_flagged_as_bleed():
    # "diagnosis" carries an -osis suffix but is common clinical prose, not an entity: the negative
    # lookbehind keeps it out of medical_entities, so a premise lacking the word "diagnosis" does
    # NOT bleed-flag the claim (the real entity "glioma" IS present in the premise).
    claim = "The most likely diagnosis is glioma [2]."
    premise = ("The most likely lesion is an insular glioma; gross-total resection of the glioma "
               "is the operative goal.")
    v = verify_answer(claim, {"2": premise})
    verdict = v.claims[0]
    assert verdict.bleed_terms == []
    assert verdict.supported is True
    assert v.n_unsupported == 0


def test_plural_claim_entity_matches_singular_premise():
    # Singular/plural normalization: a pluralized claim entity ("meningiomas") matches its singular
    # premise form ("meningioma") instead of false-flagging as a bleed.
    claim = "Meningiomas are the most common tumor [2]."
    premise = "Meningioma is the most common primary intracranial tumor in adults."
    v = verify_answer(claim, {"2": premise})
    verdict = v.claims[0]
    assert verdict.bleed_terms == []
    assert verdict.supported is True
    assert v.n_unsupported == 0


def test_thin_premise_abstains_from_bleed_check():
    # An [L#] claim whose cited premise is empty (e.g. a missing PubMed abstract) is too thin to
    # judge: the guard abstains (no bleed) rather than flagging an entity it cannot disprove.
    claim = "Metastasis is common in this setting [L1]."
    v = verify_answer(claim, {"L1": ""})
    assert v.n_cited_claims == 1
    verdict = v.claims[0]
    assert verdict.bleed_terms == []
    assert verdict.supported is True
    assert v.n_unsupported == 0
