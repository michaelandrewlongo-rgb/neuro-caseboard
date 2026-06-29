"""The factored builders match the inline construction the synth functions used."""
from dataclasses import dataclass


@dataclass
class _Hit:
    book: str; chapter: str; page: int; text: str
    has_figure: bool = False; figure_path: str = None


@dataclass
class _Fig:
    source_n: int; book: str; chapter: str; page: int; caption: str = ""


def test_build_citations_numbers_hits_then_appends_figures():
    from neuro_core.synthesize import build_citations
    hits = [_Hit("BookA", "Ch1", 10, "passage one"),
            _Hit("BookB", "", 20, "passage two")]
    # an appended figure has source_n > len(hits)
    figs = [_Fig(source_n=3, book="BookC", chapter="Ch9", page=30, caption="a plate")]
    cites = build_citations(hits, figs)
    assert [(c.n, c.book, c.page) for c in cites] == [
        (1, "BookA", 10), (2, "BookB", 20), (3, "BookC", 30)]
    assert cites[0].text == "passage one"      # hit citations carry the chunk text
    assert cites[2].text == ""                 # appended-figure citation has no chunk text


def test_build_synth_prompt_contains_question_and_passages():
    from neuro_core.synthesize import build_synth_prompt
    hits = [_Hit("BookA", "Ch1", 10, "passage one")]
    p = build_synth_prompt("what supplies X?", hits, [], variant_directive="Answer for 'left' ONLY.")
    assert "Question: what supplies X?" in p
    assert "[1] BookA, Ch1, p.10:" in p
    assert "Answer for 'left' ONLY." in p


def test_build_woven_prompt_includes_studies_block():
    from neuro_caseboard.woven_synth import build_woven_prompt
    hits = [_Hit("BookA", "Ch1", 10, "passage one")]

    @dataclass
    class _Rec:
        n: int = 1; title: str = "A study"; journal: str = "J"; year: int = 2021
        authors: str = "Doe"; abstract: str = "abstract text"; pmid: str = "1"
    p = build_woven_prompt("q", hits, [], [_Rec()])
    assert "Textbook passages:" in p
    assert "Contemporary studies:" in p
