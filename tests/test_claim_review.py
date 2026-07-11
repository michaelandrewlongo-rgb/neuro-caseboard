"""SP1 — the Clinical Claim Review gate (FIX_PLAN §5). Deterministic, model-free.

Locked thresholds (domain-blind advisory 2026-07-11): STALENESS_YEARS=5 (soft cues),
strong-cue tier = ceil(0.6*5) = 3; a strong-cue claim citing no dated marker also flags.
Fail action = soften (uncertain claims are carried, never deleted): assert prose == answer.
"""
from neuro_caseboard.claim_review import (
    build_decision_card, category, currency_cue, is_stale,
)
from neuro_caseboard.evidence_spans import EvidenceSpan


# --- category tagging -------------------------------------------------------------------------

def test_category_threshold():
    assert category("The door-to-groin threshold is 6 hours.") == "threshold"


def test_category_comparative():
    assert category("Thrombectomy is superior to thrombolysis alone.") == "comparative"


def test_category_regulatory():
    assert category("The device is FDA approved for this indication.") == "regulatory"


def test_category_contraindication():
    assert category("It is contraindicated in coagulopathy.") == "contraindication"


def test_category_indication():
    assert category("It is indicated for large-vessel occlusion.") == "indication"


def test_category_connective_is_other():
    assert category("This reflects the underlying vascular anatomy.") == "other"


# --- currency cue tiering ---------------------------------------------------------------------

def test_currency_cue_strong():
    assert currency_cue("This is the latest approach.") == "strong"
    assert currency_cue("It was newly approved.") == "strong"


def test_currency_cue_soft():
    assert currency_cue("This is now the standard of care.") == "soft"
    assert currency_cue("The current recommendation favors it.") == "soft"


def test_currency_cue_none():
    assert currency_cue("The mechanism is vasogenic edema.") is None


# --- staleness (5y soft / 3y strong; strong + no dated marker = stale) ------------------------

def test_no_cue_never_stale():
    assert is_stale(None, 1990, 2026) is False


def test_soft_cue_5y_boundary():
    assert is_stale("soft", 2018, 2026) is True     # gap 8 > 5
    assert is_stale("soft", 2022, 2026) is False    # gap 4 <= 5


def test_strong_cue_3y_boundary():
    assert is_stale("strong", 2022, 2026) is True   # gap 4 > 3
    assert is_stale("strong", 2024, 2026) is False  # gap 2 <= 3


def test_undated_marker_only_strong_flags():
    assert is_stale("strong", None, 2026) is True   # "latest" with no dated source = suspect
    assert is_stale("soft", None, 2026) is False    # "current standard" citing a textbook is fine


# --- card assembly ----------------------------------------------------------------------------

def _span(claim, marker="1", quote="q", matched=True):
    return EvidenceSpan(claim=claim, marker=marker, quote=quote, matched=matched, score=1.0)


def test_settled_indication_reaches_bottom_line():
    card = build_decision_card(
        "It is indicated for large-vessel occlusion [1].",
        spans=[_span("It is indicated for large-vessel occlusion [1].")],
        marker_year={"1": None}, now_year=2026)
    assert card.prose == "It is indicated for large-vessel occlusion [1]."
    assert [c.category for c in card.bottom_line] == ["indication"]
    assert card.bottom_line[0].status == "settled"


def test_threshold_reaches_decision_furniture():
    card = build_decision_card(
        "The threshold is 6 hours [1].",
        spans=[_span("The threshold is 6 hours [1].")],
        marker_year={"1": None}, now_year=2026)
    assert [c.category for c in card.decision_furniture] == ["threshold"]


def test_unmatched_span_is_uncertain():
    card = build_decision_card(
        "It is indicated for X [1].",
        spans=[_span("It is indicated for X [1].", matched=False)],
        marker_year={"1": None}, now_year=2026)
    assert card.bottom_line == []
    assert len(card.uncertainties) == 1
    assert "unmatched_span" in card.uncertainties[0].flags


def test_stale_strong_currency_is_uncertain():
    card = build_decision_card(
        "This is the latest approved device [L1].",
        spans=[_span("This is the latest approved device [L1].", marker="L1")],
        marker_year={"L1": 2019}, now_year=2026)   # strong cue, gap 7 > 3
    assert len(card.uncertainties) == 1
    assert "stale_currency" in card.uncertainties[0].flags


def test_coverage_gap_surfaces_unaddressed_limb():
    card = build_decision_card(
        "Alpha is preferred [1].",
        spans=[_span("Alpha is preferred [1].")],
        marker_year={"1": None}, now_year=2026,
        question="Compare alpha and beta")
    assert any("beta" in g.lower() for g in card.coverage_gaps)


def test_prose_is_verbatim_and_empty_is_safe():
    # No spans, empty question — must not raise, prose preserved (soften-not-hide invariant).
    card = build_decision_card("Plain answer with no cited claims.", spans=[],
                               marker_year={}, now_year=2026)
    assert card.prose == "Plain answer with no cited claims."
    assert card.bottom_line == [] and card.uncertainties == []
