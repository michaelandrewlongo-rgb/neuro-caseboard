import pytest

from neuro_core.live_reconcile import build_pubmed_query


class FakeSynth:
    def __init__(self, reply):
        self.reply = reply
        self.captured = None

    def generate(self, system, user, images):
        self.captured = {"system": system, "user": user, "images": images}
        return self.reply


def test_build_pubmed_query_parses_terms_and_pubtypes():
    synth = FakeSynth('{"terms":"tenecteplase OR alteplase stroke",'
                      '"pub_types":["Randomized Controlled Trial","Meta-Analysis"]}')
    terms, pub_types = build_pubmed_query("Is tenecteplase better than alteplase?",
                                          synth)
    assert terms == "tenecteplase OR alteplase stroke"
    assert pub_types == ["Randomized Controlled Trial", "Meta-Analysis"]
    assert "Is tenecteplase" in synth.captured["user"]


def test_build_pubmed_query_drops_unknown_pubtypes():
    synth = FakeSynth('{"terms":"glioma","pub_types":["Editorial","Meta-Analysis"]}')
    terms, pub_types = build_pubmed_query("low grade glioma?", synth)
    assert pub_types == ["Meta-Analysis"]   # "Editorial" not in the allowed set


def test_build_pubmed_query_raises_on_empty_terms():
    with pytest.raises(ValueError):
        build_pubmed_query("x", FakeSynth('{"terms":"","pub_types":[]}'))


def test_build_pubmed_query_raises_on_garbage():
    with pytest.raises(ValueError):
        build_pubmed_query("x", FakeSynth("the model rambled, no json"))


def test_build_pubmed_query_handles_fenced_reply():
    synth = FakeSynth('```json\n{"terms":"stroke thrombolysis","pub_types":[]}\n```')
    terms, pub_types = build_pubmed_query("Stroke tx?", synth)
    assert terms == "stroke thrombolysis"
    assert pub_types == []


def test_build_pubmed_query_non_list_pubtypes_does_not_crash():
    synth = FakeSynth('{"terms":"glioma","pub_types":42}')
    terms, pub_types = build_pubmed_query("glioma?", synth)
    assert terms == "glioma"
    assert pub_types == []


def test_build_pubmed_query_raises_on_null_terms():
    import pytest
    with pytest.raises(ValueError):
        build_pubmed_query("x", FakeSynth('{"terms":null,"pub_types":[]}'))
