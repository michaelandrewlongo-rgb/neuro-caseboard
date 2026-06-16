"""The 8-surface case taxonomy — pure data, topic-agnostic.

Pins the section set/order from LOOP_PROMPT §0, that the reused sections match the build files
(so no fork), and that slot labels Title-Case deterministically.
"""

from neuro_caseboard.case_sections import (
    CASE_SECTIONS, CASE_ORDER, CASE_HEADINGS, CASE_INTROS, SLOT_LABEL,
)


def test_eight_sections_in_prompt_order():
    headings = [CASE_HEADINGS[tf] for tf in CASE_ORDER]
    assert headings == [
        "Clinical Summary", "Clinical Reasoning", "Operative Plan", "Alternatives",
        "Risks", "Pre-op Optimization", "Surgical Technique", "Case Figures",
    ]
    assert len(CASE_SECTIONS) == 8
    assert len(CASE_ORDER) == len(CASE_HEADINGS) == len(CASE_INTROS) == 8


def test_reused_sections_match_the_build_files():
    # Operative Plan / Risks reuse the existing build target files verbatim (no fork).
    assert "04-operative-plan.md" in CASE_ORDER
    assert "05-risk-and-rescue.md" in CASE_ORDER


def test_every_section_has_intro_and_slots():
    for s in CASE_SECTIONS:
        assert s.heading and s.intro
        assert s.slots and all(isinstance(k, str) and k for k in s.slots)


def test_slot_label_title_cases_keys():
    assert SLOT_LABEL["working_diagnosis"] == "Working Diagnosis"
    assert SLOT_LABEL["named_adjuncts"] == "Named Adjuncts"
    # every slot of every section has a label
    for s in CASE_SECTIONS:
        for k in s.slots:
            assert k in SLOT_LABEL
