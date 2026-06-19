"""Feedback model + JSON round-trip + heading→target_file resolver."""
import pytest

from neuro_caseboard.feedback import (
    MARKS,
    CaseFeedback,
    FeedbackItem,
    load_feedback,
    save_feedback,
    target_file_for_heading,
)


def test_marks_axis():
    assert set(MARKS) == {"wrong", "missing", "important"}


def test_item_rejects_unknown_mark():
    with pytest.raises(ValueError):
        FeedbackItem(mark="bogus", text="x")


def test_heading_resolves_to_target_file():
    assert target_file_for_heading("Anatomy at Risk") == "03-anatomy-at-risk.md"
    assert target_file_for_heading("Operative Plan") == "04-operative-plan.md"
    assert target_file_for_heading("Risk and Rescue") == "05-risk-and-rescue.md"
    assert target_file_for_heading("") == "04-operative-plan.md"  # sensible default


def test_round_trip(tmp_path):
    fb = CaseFeedback(topic="C5-6 corpectomy", profile="spine", items=[
        FeedbackItem(mark="important", text="Vertebral artery course", target_file="03-anatomy-at-risk.md"),
        FeedbackItem(mark="missing", text="Confirm fusion construct plan", note="I always fuse"),
    ])
    p = save_feedback(fb, tmp_path / "marks.json")
    assert load_feedback(p) == fb
