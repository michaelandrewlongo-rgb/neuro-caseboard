"""Cross-section near-duplicate collapse (#9). Deterministic, topic-agnostic: keep the
first occurrence, replace later ones with a cross-reference. No phrase blacklists."""

from neuro_caseboard.model import Claim, Section
from neuro_caseboard.dedup import dedup_sections


def _claim(text, status="supported"):
    return Claim(text=text, why="because", status=status)


def test_exact_duplicate_across_sections_is_collapsed():
    closure = "Watertight dural closure with a graft; layered closure over a drain"
    secs = [
        Section(heading="Operative Plan", claims=[_claim(closure)]),
        Section(heading="Risk and Rescue", claims=[_claim(closure), _claim("Distinct risk item")]),
    ]
    out = dedup_sections(secs)
    op, risk = out
    # first occurrence kept
    assert any(c.text == closure for c in op.claims)
    # later occurrence removed from Risk, distinct one survives
    assert all(c.text != closure for c in risk.claims)
    assert any(c.text == "Distinct risk item" for c in risk.claims)
    # a cross-reference points back to the first section
    assert any("Operative Plan" in ref for ref in risk.cross_refs)


def test_near_verbatim_duplicate_is_collapsed():
    a = "Watertight dural closure with a fascial graft; layered closure over a subgaleal drain"
    b = "Watertight dural closure using a fascial graft; layered closure over a subgaleal drain"
    secs = [
        Section(heading="Operative Plan", claims=[_claim(a)]),
        Section(heading="Risk and Rescue", claims=[_claim(b)]),
    ]
    out = dedup_sections(secs)
    assert len(out[1].claims) == 0
    assert out[1].cross_refs


def test_distinct_claims_are_both_kept():
    secs = [
        Section(heading="Operative Plan", claims=[_claim("Drill the corpectomy trough")]),
        Section(heading="Risk and Rescue", claims=[_claim("Anticipate vertebral artery injury")]),
    ]
    out = dedup_sections(secs)
    assert len(out[0].claims) == 1 and len(out[1].claims) == 1
    assert not out[0].cross_refs and not out[1].cross_refs


def test_similar_claims_within_one_section_are_not_collapsed():
    secs = [
        Section(heading="Operative Plan", claims=[
            _claim("Confirm the level with fluoroscopy"),
            _claim("Confirm the level with fluoroscopy again"),
        ]),
    ]
    out = dedup_sections(secs)
    assert len(out[0].claims) == 2
