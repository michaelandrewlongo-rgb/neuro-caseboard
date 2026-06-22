from types import SimpleNamespace

from neuro_caseboard.qa import _answer_question_woven, QAResult
from neuro_caseboard.literature.config import LiteratureConfig
from neuro_caseboard.literature.retriever import LiteratureRecord
from neuro_core.query import RetrievalBundle, Clarification
from neuro_core.query_analyze import VariantRewrite
from neuro_core.index import Hit


def _cfg():
    return LiteratureConfig(enabled=True, recency_years=7, k=5, cache_ttl_days=14,
                            ncbi_api_key="", cache_dir="/tmp/x", weave=True,
                            recency_boost=0, precision_gate=True, precision_min_overlap=1)


def _bundle(question="q", variant=None):
    return RetrievalBundle(question=question,
                           hits=[Hit(id="a", book="B", chapter="C", page=1, text="t1")],
                           figures=[], images=[], variant=variant)


def _rec(pmid="111"):
    return LiteratureRecord(pmid=pmid, title="T", journal="J", year=2024, doi="d", url="u",
                            abstract="a", sections={}, pub_types=["Review"])


class _Synth:
    def __init__(self, reply):
        self.reply = reply

    def generate(self, system, user, images):
        return self.reply


def test_woven_happy_path_one_block_two_namespaces():
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Answer [1] with trial [L1]."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec("111")])
    assert isinstance(out, QAResult)
    assert out.answer == "Answer [1] with trial [L1]."
    assert [c.n for c in out.citations] == [1]
    assert out.literature is not None
    assert out.literature.narrative == ""             # prose is woven into `answer`
    assert [c.n for c in out.literature.citations] == [1]
    assert out.literature.citations[0].pmid == "111"


def test_woven_no_records_literature_is_none():
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Textbook only [1]."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [])
    assert out.answer == "Textbook only [1]."
    assert out.literature is None


def test_woven_clarification_short_circuits():
    clar = Clarification(question="q", variants=[VariantRewrite("A", "a"),
                                                 VariantRewrite("B", "b")])
    out = _answer_question_woven("q", lit_config=_cfg(), synth_client=_Synth("x"),
                                 plan_a=lambda: clar, retrieve_b=lambda: [_rec()])
    assert out is clar


def test_woven_refusal_drops_citations_and_literature():
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Not found in the provided sources."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec()])
    assert out.answer == "Not found in the provided sources."
    assert out.citations == []
    assert out.figures == []
    assert out.literature is None


def test_woven_empty_answer_retries_then_refuses():
    calls = {"n": 0}

    class _EmptySynth:
        def generate(self, system, user, images):
            calls["n"] += 1
            return "   "  # always empty/whitespace

    out = _answer_question_woven("q", lit_config=_cfg(), synth_client=_EmptySynth(),
                                 plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec()])
    assert out.answer == "Not found in the provided sources."
    assert calls["n"] == 2  # one retry, then degrade


def test_woven_variant_prepends_assuming_line():
    vr = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    out = _answer_question_woven(
        "q", lit_config=_cfg(), synth_client=_Synth("Body [1]."),
        plan_a=lambda: _bundle(question="uni rewrite", variant=vr),
        retrieve_b=lambda: [])
    assert out.answer.startswith("**Assuming unilateral FTP hemicraniectomy")
    assert "Body [1]." in out.answer


def test_woven_lane_b_failure_is_additive():
    def boom():
        raise RuntimeError("pubmed down")

    out = _answer_question_woven("q", lit_config=_cfg(), synth_client=_Synth("Textbook [1]."),
                                 plan_a=lambda: _bundle(), retrieve_b=boom)
    assert out.answer == "Textbook [1]."
    assert out.literature is None  # literature failure never blocks the answer


def test_woven_attaches_verification():
    out = _answer_question_woven("q", lit_config=_cfg(),
        synth_client=_Synth("The MCA supplies lateral cortex [1]. EVT helps [L1]."),
        plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec("111")])
    assert isinstance(out, QAResult)
    assert out.verification is not None
    assert out.verification.n_cited_claims == 2


def test_woven_flags_unsupported_literature_claim():
    """SHOULD-1/2 (woven path): alignment-sensitive — the [L1] premise comes from the
    record's abstract. With an off-topic abstract (≥5 content tokens) the LexicalVerifier
    must flag the [L1] claim unsupported, proving the literature premise wiring is aligned."""
    # Custom hit text supports the textbook [1] claim; the literature abstract is unrelated
    # to the [L1] claim, so only [L1] should fail.
    bundle = RetrievalBundle(
        question="q",
        hits=[Hit(id="a", book="B", chapter="C", page=1,
                  text="The middle cerebral artery supplies the lateral cerebral cortex.")],
        figures=[], images=[], variant=None)
    off_topic = LiteratureRecord(
        pmid="111", title="T", journal="J", year=2024, doi="d", url="u",
        abstract="The corpus callosum is a broad commissural white-matter tract "
                 "connecting the two cerebral hemispheres.",
        sections={}, pub_types=["Review"])
    out = _answer_question_woven(
        "q", lit_config=_cfg(),
        synth_client=_Synth("The MCA supplies the lateral cortex [1]. "
                            "Endovascular thrombectomy improves distal-occlusion outcomes [L1]."),
        plan_a=lambda: bundle, retrieve_b=lambda: [off_topic])
    assert isinstance(out, QAResult)
    assert out.verification.n_cited_claims == 2
    assert out.verification.n_unsupported == 1
    assert "L1" in out.verification.unsupported_markers()
    assert "1" not in out.verification.unsupported_markers()
