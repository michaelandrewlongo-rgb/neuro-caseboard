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
