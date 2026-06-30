"""stream_answer emits sources/figures before tokens, an authoritative answer, then done."""
from dataclasses import dataclass, field
from neuro_caseboard.qa_stream import stream_answer


@dataclass
class _Hit:
    book: str = "BookA"; chapter: str = "Ch1"; page: int = 10; text: str = "passage"
    has_figure: bool = False; figure_path: str = None


@dataclass
class _Bundle:
    question: str; hits: list; figures: list = field(default_factory=list)
    images: list = field(default_factory=list); variant: object = None


class _FakeStreamClient:
    def __init__(self, parts): self._parts = parts
    def generate(self, system, user, images): return "".join(self._parts)
    def generate_stream(self, system, user, images):
        for p in self._parts: yield p


def _collect(**kw):
    events = []
    stream_answer("q", events.append, **kw)
    return events


def test_order_sources_before_tokens_then_authoritative_answer():
    bundle = _Bundle("q", [_Hit()], figures=[])
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["Hel", "lo [1]"]),
    )
    types = [e["type"] for e in events]
    assert types.index("sources") < types.index("answer_delta")
    assert types.index("figures") < types.index("answer_delta")
    assert types[-1] == "done"
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["answer"] == "Hello [1]"          # == concatenated deltas
    assert answer_ev["refusal"] is False
    assert [e["text"] for e in events if e["type"] == "answer_delta"] == ["Hel", "lo [1]"]


def test_refusal_drops_sources_and_figures():
    @dataclass
    class _Fig:
        source_n: int = 1; book: str = "B"; chapter: str = ""; page: int = 1; caption: str = ""
    bundle = _Bundle("q", [_Hit()], figures=[_Fig()])
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["Not found in the provided sources."]),
    )
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["refusal"] is True
    assert answer_ev["citations"] == [] and answer_ev["figures"] == []


def test_emit_batch_marks_refusal_and_drops_sources():
    # The non-woven blocking fallback (_emit_batch) must wire a refusal as refusal:True with empty
    # sources/figures, not a clean-looking answer beside a populated Sources list.
    from neuro_caseboard.qa import QAResult
    from neuro_caseboard.qa_stream import _emit_batch
    from neuro_core.synthesize import REFUSAL
    events = []
    qr = QAResult(answer=REFUSAL, citations=[object()], figures=[object()], literature=None)
    _emit_batch(events.append, qr)
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["refusal"] is True
    assert answer_ev["citations"] == [] and answer_ev["figures"] == []
    assert next(e for e in events if e["type"] == "sources")["citations"] == []
    assert next(e for e in events if e["type"] == "figures")["figures"] == []


def test_clarification_short_circuits():
    from neuro_core.query import Clarification
    events = _collect(
        plan_a=lambda: Clarification(question="q", variants=[]),
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["x"]),
    )
    assert [e["type"] for e in events] == ["clarification", "done"]


def test_streaming_verifies_body_not_the_disambiguation_prefix():
    # The "**Assuming <variant>**" prefix is a system annotation, not a clinical claim. Verifying
    # prefix+body merges the prefix into the first sentence (it ends ".**\n\n", which the sentence
    # splitter does not break on), so a variant label carrying a medical-suffix word (e.g.
    # "hemicraniectomy") false-flags via the bleed path. Verification must run on the BODY only,
    # matching the blocking path (qa.answer_question verifies the un-prefixed answer).
    from neuro_core.query import VariantRewrite
    hit_text = "The flap is raised over the frontotemporoparietal region and the bone removed widely."
    bundle = _Bundle("q", [_Hit(text=hit_text)],
                     variant=VariantRewrite(label="unilateral FTP hemicraniectomy", rewrite="q"))
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(
            ["The flap is raised over the frontotemporoparietal region [1]."]),
    )
    ver = next(e for e in events if e["type"] == "verification")["verification"]
    assert ver is not None
    assert ver.n_unsupported == 0       # the prefix's "hemicraniectomy" must NOT be verified as a claim
    assert ver.bleed_terms() == []


def test_variant_prefix_is_first_delta():
    from neuro_core.query import VariantRewrite
    bundle = _Bundle("q", [_Hit()], variant=VariantRewrite(label="left ICA", rewrite="q left"))
    events = _collect(
        plan_a=lambda: bundle,
        retrieve_b=lambda: [],
        synth_client=_FakeStreamClient(["body [1]"]),
    )
    deltas = [e["text"] for e in events if e["type"] == "answer_delta"]
    assert deltas[0].startswith("**Assuming left ICA")
    answer_ev = next(e for e in events if e["type"] == "answer")
    assert answer_ev["answer"] == "".join(deltas)      # persisted final == streamed
