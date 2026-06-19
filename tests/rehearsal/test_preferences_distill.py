"""Distil marks into reusable, reinforced, profile-keyed preferences."""
from neuro_caseboard.feedback import CaseFeedback, FeedbackItem
from neuro_caseboard.preferences import (
    distill, save_preferences, load_preferences, _key_terms,
)


def _fb(topic, *items):
    return CaseFeedback(topic=topic, profile="spine", items=list(items))


def test_marks_map_to_actions():
    prefs = distill(_fb("C5-6 corpectomy",
                        FeedbackItem(mark="wrong", text="Generic positioning checklist"),
                        FeedbackItem(mark="important", text="Vertebral artery course"),
                        FeedbackItem(mark="missing", text="Confirm fusion construct plan")))
    assert {p.action for p in prefs} == {"suppress", "elevate", "add"}
    assert all(p.profile == "spine" for p in prefs)
    assert all(p.weight == 1 for p in prefs)


def test_reinforce_repeat_across_cases():
    p1 = distill(_fb("C5-6 corpectomy", FeedbackItem(mark="wrong", text="Generic positioning checklist")))
    p2 = distill(_fb("C1-2 fusion", FeedbackItem(mark="wrong", text="checklist for generic positioning")),
                 p1)  # same key terms
    assert len(p2) == 1 and p2[0].weight == 2
    assert set(p2[0].sources) == {"C5-6 corpectomy", "C1-2 fusion"}


def test_key_terms_order_independent():
    assert _key_terms("Vertebral artery course") == _key_terms("course of the artery, vertebral")


def test_round_trip(tmp_path):
    prefs = distill(_fb("t", FeedbackItem(mark="wrong", text="Generic positioning checklist")))
    p = save_preferences(prefs, tmp_path / "p.json")
    assert load_preferences(p) == prefs
    assert load_preferences(tmp_path / "absent.json") == []
