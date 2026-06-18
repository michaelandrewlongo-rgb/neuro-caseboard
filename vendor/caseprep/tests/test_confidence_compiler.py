
"""Tests for confidence rendering in the compiler."""

import pytest
from caseprep.compile.case_compiler import _confidence_band
from caseprep.core.contracts import SlotConfidence


def test_confidence_band_high():
    sc = SlotConfidence(logprob=-0.1, entropy=0.2)
    assert _confidence_band(sc) == "low"


def test_confidence_band_medium():
    sc = SlotConfidence(logprob=-2.0, entropy=1.0)
    assert _confidence_band(sc) == "low"


def test_confidence_band_low():
    sc = SlotConfidence(logprob=-5.0, entropy=2.0)
    assert _confidence_band(sc) == "low"


def test_confidence_band_none():
    assert _confidence_band(None) == ""
