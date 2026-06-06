# tests/test_synthesize.py
from engine.synthesize import synthesize, SYSTEM_PROMPT, _format_passages
from engine.index import Hit


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
