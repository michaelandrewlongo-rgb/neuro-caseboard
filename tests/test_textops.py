"""Topic-agnostic text helpers: compound-bullet splitting (#6) and question scrubbing."""

import pytest

from neuro_caseboard.textops import split_compound, scrub_question
import tests.fixtures as fx


def test_splits_multi_question_bullet_into_clauses():
    text = ("SSEP and MEP for upper and lower extremities? "
            "Free-run and triggered EMG for C5-C6 myotomes? "
            "Baseline signals before final positioning?")
    parts = split_compound(text)
    assert len(parts) == 3
    assert all(p.endswith("?") for p in parts)
    assert "SSEP and MEP" in parts[0]


def test_splits_semicolon_list_when_two_or_more():
    text = ("Watertight dural closure if durotomy occurs; anterior plate and cage "
            "reconstruction; layered closure over a subfascial drain")
    parts = split_compound(text)
    assert len(parts) == 3
    assert "anterior plate" in parts[1]


def test_splits_enumerated_steps():
    text = "(1) identify the plane; (2) debulk internally; (3) dissect the capsule"
    parts = split_compound(text)
    assert len(parts) == 3
    assert parts[0].startswith("identify") or parts[0].startswith("(1)")


def test_single_question_is_not_compound():
    assert split_compound("Confirm the bifurcation height relative to the mandible?") == []


def test_plain_statement_is_not_compound():
    assert split_compound("Confirm vertebral artery course and trough width") == []


@pytest.mark.parametrize("topic", fx.ALL_TOPICS)
def test_every_subspecialty_monitoring_card_splits(topic):
    """The planted compound monitoring card must split for every subspecialty."""
    data = fx._TOPICS[topic]
    q, _ = data["monitoring_compound"]
    assert len(split_compound(q)) >= 2


def test_splits_long_multi_sentence_rescue_bullet():
    # dense rescue prose (multiple scenarios in one bullet) -> per-sentence checkboxes
    text = ("VA injury: pack with muscle and Surgicel, consider primary repair. "
            "IONM loss: warm irrigation, raise MAP, release retraction. "
            "Cord swelling: widen decompression and give IV steroids. "
            "Air embolism: flood the field and place in Trendelenburg.")
    parts = split_compound(text)
    assert len(parts) == 4
    assert parts[0].startswith("VA injury")


def test_short_two_sentence_bullet_is_not_split():
    assert split_compound("Confirm the level. Then expose the disc space.") == []


def test_scrub_strips_explorer_tokens():
    assert scrub_question("VERIFY: Confirm level [needs_patient_fact]") == "Confirm level"
    assert "[needs_evidence]" not in scrub_question("Check this [needs_evidence]")
