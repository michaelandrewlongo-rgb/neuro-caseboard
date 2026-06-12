"""Anti-bleed guard: strip cross-region (CPA / posterior-fossa / skull-base) content from
a topic that is clearly supratentorial/other-region. Defense-in-depth for both the LLM
and the deterministic Explorer paths."""

from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest
from neuro_caseboard.guard import prune_offtarget


def _c(q, w="why it matters"):
    return QuestionCard(target_file="03-anatomy-at-risk.md", section_key="neural_structures",
                        question=q, why_it_matters=w, compiler_slot="Neural Structures")


def _mani(*cards):
    return QuestionManifest(procedure_family="t", cards=list(cards))


CPA_CARD = _c("AICA loop and cerebellopontine angle relationship to the tumor capsule")
CN_LITANY = _c("Which cranial nerves (CN V, VII, VIII, IX-XI) are at risk? Brainstem compression?")
CONVEXITY_OK = _c("Cortical draining veins and superior sagittal sinus along the tumor margin")


def test_prunes_cpa_content_on_supratentorial_topic():
    m = prune_offtarget(_mani(CPA_CARD, CN_LITANY, CONVEXITY_OK),
                        "right frontal non-eloquent convexity meningioma resection")
    qs = " ".join(c.question for c in m.cards)
    assert "cerebellopontine" not in qs.lower()
    assert "IX-XI" not in qs
    assert "draining veins" in qs  # the legitimate convexity card survives


def test_keeps_cpa_content_on_posterior_topic():
    m = prune_offtarget(_mani(CPA_CARD, CN_LITANY, CONVEXITY_OK),
                        "left vestibular schwannoma, retrosigmoid resection")
    assert len(m.cards) == 3  # genuine CPA case — nothing is off-target


def test_no_change_when_no_bleed():
    m = prune_offtarget(_mani(CONVEXITY_OK), "right frontal convexity meningioma")
    assert len(m.cards) == 1


def test_brainstem_complication_is_not_treated_as_bleed():
    # "brainstem injury" is a legitimate catastrophic complication on a cranial case;
    # it must NOT be pruned (it is not CPA-specific anatomy).
    card = _c("Major arterial injury causing stroke or brainstem injury", "rescue needed")
    m = prune_offtarget(_mani(card), "pterional craniotomy for MCA aneurysm clipping")
    assert len(m.cards) == 1
