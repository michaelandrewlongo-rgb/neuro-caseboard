# tests/test_synthesize.py
from neuro_core.synthesize import (
    synthesize, SYSTEM_PROMPT, REFUSAL, is_refusal, _format_passages)
from neuro_core.index import Hit


def test_prompt_still_embeds_the_refusal_string():
    # The constant refactor must not change the instruction the model sees.
    assert f'"{REFUSAL}"' in SYSTEM_PROMPT
    assert REFUSAL == "Not found in the provided sources."


def test_is_refusal_matches_contract_with_normalization():
    assert is_refusal(REFUSAL)
    assert is_refusal("Not found in the provided sources.")
    assert is_refusal("Not found in the provided sources")        # no period
    assert is_refusal("  Not found in the provided sources.\n")   # whitespace
    assert is_refusal("not found in the provided sources.")       # case


def test_is_refusal_false_for_real_answers():
    assert not is_refusal("The cavernous sinus contains CN III-VI [1].")
    assert not is_refusal("")
    # mentions the phrase but is a real answer -> equality (not substring) -> False
    assert not is_refusal(
        "Not found in the provided sources for dosing, but [1] gives the range.")


class FakeSynthClient:
    def __init__(self):
        self.captured = {}

    def generate(self, system, user, images):
        self.captured = {"system": system, "user": user, "images": images}
        return "ICP is 5-15 mmHg [1]."


class FakeFigure:
    def __init__(self, source_n, book, page):
        self.source_n = source_n
        self.book = book
        self.page = page


def _hit():
    return Hit(id="x", book="NeuroICU", chapter="Pressure", page=10,
               text="normal icp is 5 to 15 mmHg")


def test_synthesize_builds_prompt_and_citations():
    client = FakeSynthClient()
    out = synthesize("normal icp?", [_hit()], figures=[], images=[],
                     synth_client=client)
    assert out.answer == "ICP is 5-15 mmHg [1]."
    assert client.captured["system"] == SYSTEM_PROMPT
    assert "[1] NeuroICU, Pressure, p.10" in client.captured["user"]
    assert "normal icp is 5 to 15 mmHg" in client.captured["user"]
    assert client.captured["images"] == []
    assert len(out.citations) == 1
    assert out.citations[0].n == 1
    assert out.citations[0].book == "NeuroICU"
    assert out.citations[0].page == 10


def test_synthesize_passes_images_and_figure_refs():
    client = FakeSynthClient()
    figs = [FakeFigure(source_n=1, book="Rhoton", page=12)]
    out = synthesize("cavernous sinus?", [_hit()], figures=figs,
                     images=[b"PNGDATA"], synth_client=client)
    assert client.captured["images"] == [b"PNGDATA"]
    assert "[1] Rhoton, p.12" in client.captured["user"]
    assert "Attached page images" in client.captured["user"]


def test_synthesize_no_hits_is_empty_refusal_path():
    assert _format_passages([]) == ""
    client = FakeSynthClient()
    out = synthesize("obscure?", [], figures=[], images=[], synth_client=client)
    assert out.citations == []
    assert client.captured["user"].rstrip().endswith("Passages:")


class FullFakeFigure:
    def __init__(self, source_n, book, chapter, page, caption):
        self.source_n = source_n
        self.book = book
        self.chapter = chapter
        self.page = page
        self.caption = caption


def test_synthesize_appends_visual_only_figure_source():
    client = FakeSynthClient()
    hit = _hit()  # one passage -> len(hits) == 1
    fig = FullFakeFigure(source_n=2, book="Rhoton", chapter="Sellar", page=531,
                         caption="cavernous sinus plate")
    out = synthesize("cs?", [hit], figures=[fig], images=[b"PNG"],
                     synth_client=client)
    user = client.captured["user"]
    assert "Additional figure sources:" in user
    assert "[2] Rhoton, Sellar, p.531 (figure)" in user
    assert "cavernous sinus plate" in user
    ns = [c.n for c in out.citations]
    assert ns == [1, 2]
    assert out.citations[1].book == "Rhoton"
    assert out.citations[1].page == 531


def test_synthesize_appends_variant_directive_to_user_message():
    from neuro_core.synthesize import synthesize
    from neuro_core.index import Hit

    class CapSynth:
        def __init__(self):
            self.user = None

        def generate(self, system, user, images):
            self.user = user
            return "ok"

    sc = CapSynth()
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    synthesize("q", hits, [], [], sc, variant_directive="DO NOT MERGE VARIANTS")
    assert "DO NOT MERGE VARIANTS" in sc.user


def test_synthesize_without_directive_is_unchanged():
    from neuro_core.synthesize import synthesize
    from neuro_core.index import Hit

    class CapSynth:
        def __init__(self):
            self.user = None

        def generate(self, system, user, images):
            self.user = user
            return "ok"

    sc = CapSynth()
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    synthesize("q", hits, [], [], sc)
    assert "never merge" not in sc.user.lower()  # no directive injected
