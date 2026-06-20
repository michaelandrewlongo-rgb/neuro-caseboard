"""Regression test for TKT-C5: Engine._answer must never surface an empty/None answer.

Root cause (evaluation/reports/root-causes/C5-disambiguation-empty-answer.md): a transient empty
`resp.text` from the synth client propagated unguarded because the only post-synthesis check is
`is_refusal()`, and `is_refusal("")` is False — so an empty string reached the caller and the
benchmark recorded SPINE-02 as not_gradable.

Fix (CHG-C5-empty-answer-guard): in `Engine._answer`, an empty-but-not-refusal synthesis result is
retried once; if still empty, the engine degrades to the honest `REFUSAL` abstention (a *gradable*
answer with no spurious citations/figures). These tests drive `_answer` with a deterministic stubbed
`synth_fn` — no live model — so the transient empty path is reproducible.
"""
from types import SimpleNamespace

from neuro_core.query import Engine, QueryResult
from neuro_core.synthesize import Synthesis, Citation, REFUSAL


class _Cfg:
    retrieve_k = 5
    rerank_k = 3
    max_figure_images = 3
    visual_retrieval = False
    visual_retrieve_k = 5


def _make_engine(synth_fn):
    eng = Engine(_Cfg(), None, None, None, synth_client=None, synth_fn=synth_fn,
                 visual_embedder=None, visual_index=None)
    # Isolate _answer from retrieval/figure collection — the guard is synth-only.
    eng._collect_figures = lambda question, top: ([], [])
    return eng


def _synth_seq(*answers):
    """A synth_fn returning the given answers in sequence (repeats the last)."""
    state = {"i": 0}

    def fn(question, top, figures, images, synth_client, **extra):
        i = state["i"]
        state["i"] += 1
        ans = answers[min(i, len(answers) - 1)]
        return Synthesis(answer=ans, citations=[Citation(1, "Book", "Chapter", 1)])

    fn.state = state
    return fn


def test_empty_then_content_retries_and_returns_content():
    fn = _synth_seq("", "real answer [1]")
    res = _make_engine(fn)._answer("q", [], None)
    assert res.answer == "real answer [1]"
    assert fn.state["i"] == 2, "should have retried the synth call exactly once"


def test_empty_twice_degrades_to_refusal():
    fn = _synth_seq("", "")
    res = _make_engine(fn)._answer("q", [], None)
    assert res.answer == REFUSAL
    assert res.citations == []
    assert res.figures == []


def test_whitespace_only_is_treated_as_empty():
    fn = _synth_seq("   \n\t  ", "content [1]")
    res = _make_engine(fn)._answer("q", [], None)
    assert res.answer == "content [1]"


def test_normal_answer_is_unchanged_and_not_retried():
    fn = _synth_seq("good answer [1]")
    res = _make_engine(fn)._answer("q", [], None)
    assert res.answer == "good answer [1]"
    assert res.citations == [Citation(1, "Book", "Chapter", 1)]
    assert fn.state["i"] == 1, "a non-empty answer must not trigger a retry"


def test_literal_refusal_is_preserved_and_not_retried():
    fn = _synth_seq(REFUSAL)
    res = _make_engine(fn)._answer("q", [], None)
    assert res.answer == REFUSAL
    assert res.citations == []
    assert res.figures == []
    assert fn.state["i"] == 1, "a genuine refusal is non-empty and must not be retried"


def test_empty_with_variant_degrades_to_bare_refusal_without_assuming_prefix():
    """The guard sits ABOVE the variant 'Assuming {label}' block, so an empty answer on a
    disambiguated/variant query must degrade to a BARE REFUSAL — never a refusal prefixed with
    'Assuming …'. Guards against a reordering regression."""
    variant = SimpleNamespace(label="Cervical", rewrite="cervical rewrite")
    fn = _synth_seq("", "")
    res = _make_engine(fn)._answer("q", [], variant)
    assert res.answer == REFUSAL
    assert "Assuming" not in res.answer
    assert res.citations == []
    assert res.figures == []
