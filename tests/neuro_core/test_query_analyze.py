# tests/neuro_core/test_query_analyze.py
from dataclasses import dataclass
from neuro_core.query_analyze import ambiguity_gate, Gate


@dataclass
class FakeHit:
    text: str


def test_gate_trips_on_taxonomy_trigger_in_question():
    # Question names the ambiguous parent procedure; passages need not.
    g = ambiguity_gate("decompressive craniectomy steps for TBI?", [])
    assert isinstance(g, Gate)
    assert g.tripped is True
    assert g.axis == "decompressive-craniectomy"


def test_gate_trips_on_two_variant_clusters_in_passages():
    # Generic question, but retrieved passages name BOTH variants of one axis.
    hits = [FakeHit("unilateral frontotemporoparietal hemicraniectomy with a large flap"),
            FakeHit("bifrontal bicoronal Kjellberg decompression in children")]
    g = ambiguity_gate("how is the bone flap fashioned?", hits)
    assert g.tripped is True
    assert g.axis == "decompressive-craniectomy"


def test_gate_clean_miss_on_unambiguous_query():
    hits = [FakeHit("the cavernous sinus contains cranial nerves III-VI")]
    g = ambiguity_gate("what are the cavernous sinus contents?", hits)
    assert g.tripped is False
    assert g.axis is None


def test_gate_does_not_trip_on_single_variant_cluster_alone():
    hits = [FakeHit("unilateral frontotemporoparietal hemicraniectomy technique")]
    g = ambiguity_gate("how is the bone flap fashioned?", hits)
    assert g.tripped is False


# ---------------------------------------------------------------------------
# Task 2 — query_analyze() + fail-open JSON parse
# ---------------------------------------------------------------------------
from neuro_core.query_analyze import query_analyze, QueryAnalysis, VariantRewrite, CLARIFY_THRESHOLD


class FakeSynth:
    def __init__(self, reply):
        self.reply = reply
        self.captured = None

    def generate(self, system, user, images):
        self.captured = {"system": system, "user": user, "images": images}
        return self.reply


_GOOD = (
    '{"ambiguous": true, "axis": "decompressive-craniectomy",'
    ' "variants": ['
    '   {"label": "unilateral FTP hemicraniectomy", "rewrite": "unilateral FTP hemicraniectomy steps"},'
    '   {"label": "bifrontal (Kjellberg) decompression", "rewrite": "bifrontal Kjellberg decompression steps"}'
    ' ], "chosen": "unilateral FTP hemicraniectomy", "confidence": 0.86}'
)


def test_query_analyze_parses_chosen_and_confidence():
    a = query_analyze("decompressive craniectomy steps?", [], FakeSynth(_GOOD))
    assert a.ambiguous is True
    assert a.chosen.label == "unilateral FTP hemicraniectomy"
    assert a.chosen.rewrite == "unilateral FTP hemicraniectomy steps"
    assert len(a.variants) == 2
    assert a.confidence == 0.86


def test_query_analyze_handles_fenced_json():
    a = query_analyze("q", [], FakeSynth("```json\n" + _GOOD + "\n```"))
    assert a.ambiguous is True


def test_query_analyze_fails_open_on_garbage():
    a = query_analyze("q", [], FakeSynth("the model rambled, no json here"))
    assert isinstance(a, QueryAnalysis)
    assert a.ambiguous is False


def test_query_analyze_not_ambiguous_when_fewer_than_two_variants():
    reply = '{"ambiguous": true, "variants": [{"label":"x","rewrite":"x"}], "chosen":"x", "confidence":0.9}'
    a = query_analyze("q", [], FakeSynth(reply))
    assert a.ambiguous is False  # a single variant is not a conflation


def test_clarify_threshold_is_a_float_between_zero_and_one():
    assert 0.0 < CLARIFY_THRESHOLD < 1.0


def test_query_analyze_not_ambiguous_when_chosen_label_missing_from_variants():
    reply = (
        '{"ambiguous": true, "variants": ['
        '  {"label": "A", "rewrite": "A steps"},'
        '  {"label": "B", "rewrite": "B steps"}'
        '], "chosen": "NONEXISTENT", "confidence": 0.9}'
    )
    a = query_analyze("q", [], FakeSynth(reply))
    assert a.ambiguous is False
