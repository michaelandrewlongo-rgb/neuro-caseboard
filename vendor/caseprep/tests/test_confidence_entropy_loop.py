
"""Tests for entropy-guided refinement loop."""

import pytest
from caseprep.confidence.entropy_loop import (
    should_refine, build_refinement_prompt,
    ENTROPY_THRESHOLD, MAX_REFINEMENTS,
)


def test_should_refine_high_entropy():
    assert should_refine(2.0, -0.5) is True


def test_should_refine_low_logprob():
    assert should_refine(0.5, -3.0) is True


def test_should_not_refine_confident():
    assert should_refine(0.3, -0.5) is False


def test_build_refinement_prompt_contains_slot_name():
    prompt = build_refinement_prompt(
        "What is the approach?", "Surgical Corridor", "entropy=2.00"
    )
    assert "Surgical Corridor" in prompt
    assert "Insufficient data" in prompt
    assert "Do NOT fabricate" in prompt


def test_threshold_constants():
    assert ENTROPY_THRESHOLD == 1.5
    assert MAX_REFINEMENTS == 1
