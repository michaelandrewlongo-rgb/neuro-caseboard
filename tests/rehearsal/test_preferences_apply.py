"""Apply preferences to a manifest: conservative suppress, plus add/elevate/profile-scope."""
from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest

from neuro_caseboard.preferences import Preference, _key_terms, apply_preferences


def _card(q):
    return QuestionCard(target_file="04-operative-plan.md", section_key="critical_steps",
                        question=q, why_it_matters="w", compiler_slot="Critical Steps")


def _m(*qs):
    return QuestionManifest(procedure_family="generic", cards=[_card(q) for q in qs])


def test_noop():
    m = _m("a step", "b step")
    assert apply_preferences(m, "spine", None) is m
    assert apply_preferences(m, "spine", []) is m


def test_single_wrong_deemphasizes_not_removes():
    m = _m("alpha step", "beta deprio target", "gamma step")
    pref = Preference(profile="spine", action="suppress",
                      pattern=_key_terms("beta deprio target"), weight=1)
    out = apply_preferences(m, "spine", [pref])
    qs = [c.question for c in out.cards]
    assert "beta deprio target" in qs        # retained — single mark never deletes
    assert qs[-1] == "beta deprio target"    # moved to end (de-emphasized)


def test_reinforced_wrong_removes():
    m = _m("alpha step", "beta deprio target", "gamma step")
    pref = Preference(profile="spine", action="suppress",
                      pattern=_key_terms("beta deprio target"), weight=2)
    out = apply_preferences(m, "spine", [pref])
    assert "beta deprio target" not in [c.question for c in out.cards]


def test_add_injects_once():
    m = _m("vertebral artery control")
    add = Preference(profile="spine", action="add", pattern=_key_terms("fusion construct plan"),
                     text="Confirm fusion construct plan", why="always")
    out = apply_preferences(m, "spine", [add])
    assert any("fusion construct plan" in c.question for c in out.cards)
    out2 = apply_preferences(out, "spine", [add])
    assert sum("fusion construct plan" in c.question for c in out2.cards) == 1


def test_elevate_moves_to_front():
    m = _m("alpha step", "beta gamma liftme", "delta step")
    pref = Preference(profile="spine", action="elevate", pattern=_key_terms("beta gamma liftme"))
    assert apply_preferences(m, "spine", [pref]).cards[0].question == "beta gamma liftme"


def test_profile_scope():
    m = _m("positioning prone checklist")
    pref = Preference(profile="skull_base", action="suppress",
                      pattern=_key_terms("positioning prone checklist"), weight=2)
    assert [c.question for c in apply_preferences(m, "spine", [pref]).cards] == ["positioning prone checklist"]
