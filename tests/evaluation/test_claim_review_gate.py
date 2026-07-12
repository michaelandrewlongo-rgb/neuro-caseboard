"""SP3 — deterministic validation of the Clinical Claim Review gate (FIX_PLAN §6).

A labeled fixture of realistic clinical claims freezes the gate's intended verdict on each, so a
later threshold/regex change that breaks one fails CI. The staleness precision floor is the repo's
hard-won discipline: the prior ⚠ badge shipped at 0.24 precision and trained the reader to ignore
it — this gate must NOT soften a claim a human marked current. now_year is pinned (never
date.today()) so the fixture does not rot.
"""
import json
from pathlib import Path

from neuro_caseboard.claim_review import (
    build_decision_card, category, currency_cue, is_stale,
)
from neuro_caseboard.evidence_spans import EvidenceSpan, span_match_rate

NOW_YEAR = 2026
FIXTURE = Path(__file__).resolve().parents[2] / "evaluation" / "claim-review" / "labeled.jsonl"


def _rows():
    return [json.loads(ln) for ln in FIXTURE.read_text().splitlines() if ln.strip()]


def _predict_stale(row) -> bool:
    return is_stale(currency_cue(row["claim"]), row["year"], NOW_YEAR)


def test_fixture_is_nonempty():
    assert len(_rows()) >= 15


def test_staleness_verdict_matches_labels_per_row():
    for row in _rows():
        assert _predict_stale(row) == row["expect_stale"], (
            f'{row["id"]}: got stale={_predict_stale(row)}, expected {row["expect_stale"]}')


def test_category_matches_labels_per_row():
    for row in _rows():
        assert category(row["claim"]) == row["expect_category"], (
            f'{row["id"]}: got {category(row["claim"])!r}, expected {row["expect_category"]!r}')


def test_staleness_precision_and_recall_floor():
    """Precision of the 'stale' verdict against the labels — the false-positive discipline. A high
    recall floor keeps genuinely stale claims from slipping through as settled."""
    tp = fp = fn = 0
    for row in _rows():
        pred, true = _predict_stale(row), row["expect_stale"]
        tp += pred and true
        fp += pred and not true
        fn += (not pred) and true
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    assert precision >= 0.9, f"staleness precision {precision:.2f} < 0.90 (false positives train distrust)"
    assert recall >= 0.8, f"staleness recall {recall:.2f} < 0.80 (stale claims slipping through)"


def test_prose_is_never_rewritten():
    """D19/D20: the card is a lens over the answer, never a rewrite. `prose` is verbatim."""
    answer = "A settled claim [1] and a stale claim [L1] with detail."
    card = build_decision_card(answer, spans=[], marker_year={}, now_year=NOW_YEAR)
    assert card.prose == answer


def test_span_match_rate_is_the_d15_metric():
    """D15: fraction of evidential quotes that string-matched their cited chunk; None when empty
    (an uncited answer has undefined verifiability, never a perfect 1.0)."""
    spans = [
        EvidenceSpan(claim="a", marker="1", quote="q", matched=True, score=1.0),
        EvidenceSpan(claim="b", marker="2", quote="q", matched=False, score=0.2),
        EvidenceSpan(claim="c", marker="D1", quote="q", matched=True, score=1.0),
    ]
    assert span_match_rate(spans) == 2 / 3
    assert span_match_rate([]) is None


def test_unmatched_span_always_routes_to_uncertain():
    """D14/D15 through the card: a quote that fails its string-match is softened, not shown settled,
    regardless of how current the claim reads."""
    span = EvidenceSpan(claim="It is indicated for X [1].", marker="1", quote="not in chunk",
                        matched=False, score=0.1)
    card = build_decision_card("It is indicated for X [1].", spans=[span],
                               marker_year={"1": None}, now_year=NOW_YEAR)
    assert card.bottom_line == []
    assert len(card.uncertainties) == 1
    assert "unmatched_span" in card.uncertainties[0].flags
