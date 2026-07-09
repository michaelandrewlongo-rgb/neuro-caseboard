"""Quoted-span verification (FIX_PLAN §3.3 / D15). The string-match core is deterministic."""
from neuro_caseboard.evidence_spans import (
    quote_matches, verify_spans, extract_and_verify, span_match_rate, EvidenceSpan)

CHUNK = ("The standard threshold is NIHSS 6 or greater for endovascular consideration. "
         "DAWN established benefit from 6 to 24 hours using clinical-imaging mismatch.")


def test_verbatim_quote_matches():
    ok, score = quote_matches("DAWN established benefit from 6 to 24 hours", CHUNK)
    assert ok and score == 1.0


def test_quote_matches_across_line_wrap_whitespace():
    ok, _ = quote_matches("the  standard\nthreshold is NIHSS 6 or greater", CHUNK)
    assert ok


def test_fabricated_quote_rejected():
    ok, score = quote_matches("DAWN showed no benefit beyond 6 hours", CHUNK)
    assert not ok and score < 0.9


def test_verify_spans_flags_missing_premise():
    spans = verify_spans([{"claim": "x", "marker": "2", "quote": "anything"}], premises={})
    assert spans[0].matched is False


def test_verify_spans_matched_and_unmatched():
    premises = {"1": CHUNK}
    items = [
        {"claim": "DAWN 6-24h", "marker": "1", "quote": "DAWN established benefit from 6 to 24 hours"},
        {"claim": "fabricated", "marker": "1", "quote": "thrombectomy is contraindicated in all cases"},
    ]
    spans = verify_spans(items, premises)
    assert spans[0].matched is True
    assert spans[1].matched is False


def test_span_match_rate_none_when_empty():
    assert span_match_rate([]) is None
    assert span_match_rate([EvidenceSpan("c", "1", "q", True, 1.0)]) == 1.0


def test_extract_and_verify_with_stub_client():
    class Stub:
        def generate(self, system, user, images):
            return '[{"claim":"DAWN 6-24h","marker":"1","quote":"DAWN established benefit from 6 to 24 hours"}]'
    spans = extract_and_verify("DAWN works [1].", {"1": CHUNK}, Stub())
    assert len(spans) == 1 and spans[0].matched is True


def test_extract_and_verify_survives_bad_json():
    class Stub:
        def generate(self, system, user, images):
            return "sorry, I cannot do that"
    assert extract_and_verify("x [1].", {"1": CHUNK}, Stub()) == []
