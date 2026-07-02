"""Lane C (corpus / [D#]) wiring: FTS query building, prompt assembly, system-rule gating,
verifier marker recognition, and the woven orchestrator's premise map + QAResult surfacing.
No LLM and no real DB — all seams are injected."""
from neuro_caseboard.corpus import CorpusRecord, _fts_match_query, format_corpus_studies
from neuro_caseboard.woven_synth import (
    WOVEN_CORPUS_RULE, WOVEN_SYSTEM, build_woven_prompt, synthesize_woven)


class _FakeSynth:
    """Records the system/user prompt it was handed and echoes a [D1]-cited claim."""

    def __init__(self):
        self.system = self.user = None

    def generate(self, system, user, images):
        self.system, self.user = system, user
        return "Large-core thrombectomy benefits selected patients [D1]."


def _rec(n=1):
    return CorpusRecord(work_id=f"w{n}", title=f"SELECT2 subgroup {n}", journal="NEJM",
                        year=2023, study_design="rct", section_type="results",
                        content="In the large-core cohort, thrombectomy improved mRS outcomes.",
                        pmid=f"3000000{n}", source_db="cerebrovascular", score=9.0)


def test_query_builder_drops_stopwords():
    q = _fts_match_query("What is the role of thrombectomy in the extended window?")
    assert q and '"thrombectomy"' in q and '"the"' not in q and " OR " in q


def test_format_bounds_excerpt():
    out = format_corpus_studies([_rec(1)], excerpt_chars=20)
    assert "[D1] SELECT2 subgroup 1 — NEJM, 2023, rct, PMID 30000001 [results]" in out
    assert "In the large-core c" in out and "improved mRS outcomes" not in out


def test_corpus_block_absent_when_no_records():
    assert "Journal literature corpus" not in build_woven_prompt("Q?", [], [], [])


def test_corpus_block_present_with_records():
    p = build_woven_prompt("Q?", [], [], [], corpus_records=[_rec(1)])
    assert "Journal literature corpus" in p and "[D1] SELECT2 subgroup 1" in p


def test_system_rule_gated_on_corpus():
    fake = _FakeSynth()
    synthesize_woven("Q?", [], [], [], [], fake)                      # no corpus
    assert fake.system == WOVEN_SYSTEM
    fake2 = _FakeSynth()
    syn = synthesize_woven("Q?", [], [], [], [], fake2, corpus_records=[_rec(1)])
    assert fake2.system == WOVEN_SYSTEM + WOVEN_CORPUS_RULE
    assert len(syn.corpus_records) == 1


def test_verifier_recognizes_D_marker():
    from neuro_caseboard.answer_verify import verify_answer
    premises = {"D1": "In the large-core cohort, thrombectomy improved mRS outcomes."}
    v = verify_answer("Thrombectomy improved mRS in large-core stroke [D1].", premises)
    assert v.n_cited_claims == 1  # [D#] is now a recognized cited claim (was invisible before)


def test_woven_orchestrator_surfaces_corpus_and_D_premises():
    from neuro_caseboard import qa

    class _Plan:
        question = "Q?"
        hits, figures, images = [], [], []
        variant = None

    fake = _FakeSynth()
    res = qa._answer_question_woven(
        "Q?", synth_client=fake,
        plan_a=lambda: _Plan(), retrieve_b=lambda: [], retrieve_c=lambda: [_rec(1)])
    assert len(res.corpus) == 1 and res.corpus[0].pmid == "30000001"
    assert res.verification is not None and res.verification.n_cited_claims == 1
    assert res.answer.strip()


class _StreamSynth:
    """Streaming fake: records the system prompt, streams a [D1]-cited claim in two deltas."""

    def __init__(self):
        self.system = None

    def generate_stream(self, system, user, images):
        self.system = system
        yield "Large-core thrombectomy benefits selected patients "
        yield "[D1]."


def test_stream_answer_wires_corpus_lane():
    """The streaming path (prod default) must run Lane C: corpus event emitted, system rule
    gated on corpus, and [D#] entailment-verified — parity with _answer_question_woven."""
    from neuro_caseboard import qa_stream

    class _Plan:
        question = "Q?"
        hits, figures, images = [], [], []
        variant = None

    events = []
    fake = _StreamSynth()
    qa_stream.stream_answer(
        "Q?", events.append, lit_config=object(), synth_client=fake,
        plan_a=lambda: _Plan(), retrieve_b=lambda: [], retrieve_c=lambda: [_rec(1)])

    corpus_ev = [e for e in events if e.get("type") == "corpus"]
    assert corpus_ev and len(corpus_ev[0]["corpus"]) == 1
    assert corpus_ev[0]["corpus"][0].pmid == "30000001"
    assert fake.system.endswith(WOVEN_CORPUS_RULE)  # rule appended only when corpus present
    verif = [e for e in events if e.get("type") == "verification"][-1]["verification"]
    assert verif is not None and verif.n_cited_claims == 1  # [D1] entailment-checked
    assert events[-1]["type"] == "done"
