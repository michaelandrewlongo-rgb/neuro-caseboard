"""Hermetic unit tests for the corpus gap-audit core (BACKLOG P1 #3).

Pure logic on an injected coverage probe — no engine, index, corpus, LLM, or network."""
from neuro_core.corpus_audit import (Topic, Coverage, GapRow, classify, audit,
                                     prioritized_gaps, render_report)
from neuro_core.high_yield_topics import HIGH_YIELD_TOPICS


def _t(key="t", consequence=3, frequency=3):
    return Topic(key=key, label=key.title(), probe_query=f"{key} query",
                 consequence=consequence, frequency=frequency)


def test_classify_covered_weak_absent():
    assert classify(Coverage(0.9, 5), strong_top=0.5, weak_top=0.2) == "covered"
    # strong top score but too few strong hits -> only weak
    assert classify(Coverage(0.9, 1), strong_top=0.5, weak_top=0.2) == "weak"
    assert classify(Coverage(0.3, 0), strong_top=0.5, weak_top=0.2) == "weak"
    assert classify(Coverage(0.1, 0), strong_top=0.5, weak_top=0.2) == "absent"


def test_audit_runs_probe_per_topic_and_records_priority():
    topics = [_t("a", 5, 4), _t("b", 2, 2)]
    canned = {"a query": Coverage(0.05, 0), "b query": Coverage(0.9, 4)}
    rows = audit(topics, lambda q: canned[q], strong_top=0.5, weak_top=0.2)
    by_key = {r.topic.key: r for r in rows}
    assert by_key["a"].status == "absent" and by_key["a"].priority == 20
    assert by_key["b"].status == "covered" and by_key["b"].priority == 4


def test_prioritized_gaps_excludes_covered_and_sorts_by_priority():
    rows = [
        GapRow(_t("low", 2, 2), "weak", Coverage(0.3, 0), 4),
        GapRow(_t("high", 5, 5), "absent", Coverage(0.0, 0), 25),
        GapRow(_t("ok", 4, 4), "covered", Coverage(0.9, 9), 16),
    ]
    gaps = prioritized_gaps(rows)
    assert [r.topic.key for r in gaps] == ["high", "low"]  # covered dropped, priority desc


def test_prioritized_gaps_absent_before_weak_on_tie():
    rows = [
        GapRow(_t("w", 3, 3), "weak", Coverage(0.3, 0), 9),
        GapRow(_t("a", 3, 3), "absent", Coverage(0.0, 0), 9),
    ]
    assert [r.status for r in prioritized_gaps(rows)] == ["absent", "weak"]


def test_render_report_lists_gaps_with_status_and_priority():
    rows = [GapRow(_t("aneurysm-rupture-rescue", 5, 5), "absent", Coverage(0.0, 0), 25)]
    md = render_report(rows)
    assert "aneurysm-rupture-rescue" in md.lower() or "Aneurysm-Rupture-Rescue" in md
    assert "absent" in md
    assert "25" in md


def test_taxonomy_includes_the_three_named_gaps():
    keys = {t.key for t in HIGH_YIELD_TOPICS}
    # the three gaps named in BACKLOG P1 #3
    assert any("rupture" in k for k in keys)        # intraprocedural aneurysm rupture rescue
    assert any("eca" in k or "anastomos" in k for k in keys)  # ECA dangerous anastomoses
    assert any("outcome" in k or "rate" in k for k in keys)   # quantitative outcomes/rates
    # every topic is well-formed
    for t in HIGH_YIELD_TOPICS:
        assert t.probe_query and 1 <= t.consequence <= 5 and 1 <= t.frequency <= 5


def test_index_probe_composes_with_audit_over_a_stubbed_engine():
    """index_probe turns engine retrieval into Coverage; audit+render then run end-to-end.
    Hermetic: a fake engine returns canned hits — no real index/corpus/network."""
    from neuro_core.corpus_audit import index_probe

    class _Hit:
        def __init__(self, score): self.score = score

    class _FakeEngine:
        def _retrieve(self, q):
            # a well-covered query returns strong hits; a gap query returns nothing
            return [_Hit(0.9), _Hit(0.8), _Hit(0.7)] if "covered" in q else []

    probe = index_probe(engine=_FakeEngine(), strong_ratio=0.6)
    assert probe("covered topic").n_strong_hits >= 2
    assert probe("missing topic") == probe("missing topic")  # deterministic
    gap = probe("missing topic")
    assert gap.top_score == 0.0 and gap.n_strong_hits == 0

    topics = [Topic("c", "Covered", "a covered query", 3, 3),
              Topic("m", "Missing", "a missing query", 5, 5)]
    rows = audit(topics, probe, strong_top=0.5, weak_top=0.2)
    md = render_report(rows)
    assert "Missing" in md and "Covered" not in md  # only the gap is in the worklist
