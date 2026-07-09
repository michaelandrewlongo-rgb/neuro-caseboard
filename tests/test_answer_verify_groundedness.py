"""D13: an answer that cites nothing has UNDEFINED groundedness (None), not 1.0.

Reporting 1.0 rewarded the exact failure the metric exists to catch — cite nothing, score
perfectly. See FIX_PLAN §6.2 D13.
"""
from neuro_caseboard.answer_verify import AnswerVerification, ClaimVerdict, verification_to_dict


def _av(n_cited, n_unsup):
    return AnswerVerification(claims=[], n_cited_claims=n_cited, n_unsupported=n_unsup)


def test_zero_cited_claims_is_none_not_one():
    assert _av(0, 0).groundedness() is None


def test_all_supported_is_one():
    assert _av(4, 0).groundedness() == 1.0


def test_partial_support_is_fraction():
    assert _av(4, 1).groundedness() == 0.75


def test_dict_serializes_none_for_uncited_answer():
    # verification_to_dict must carry None through (JSON null), not coerce to a number.
    d = verification_to_dict(_av(0, 0))
    assert d["groundedness"] is None


def test_real_uncited_answer_via_verify_answer():
    # An answer with no [n]/[L#]/[D#] markers cites nothing -> undefined groundedness.
    from neuro_caseboard.answer_verify import verify_answer

    v = verify_answer("This sentence has no citation markers at all.", premises={})
    assert v.n_cited_claims == 0
    assert v.groundedness() is None
