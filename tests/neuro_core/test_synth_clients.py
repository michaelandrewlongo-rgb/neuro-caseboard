import base64

from neuro_core.synth_clients import (
    LocalSynthClient,
    OpenRouterSynthClient,
    make_synth_client,
)


class _FakeCompletions:
    def __init__(self, parent):
        self.parent = parent

    def create(self, model, messages, temperature):
        self.parent.captured = {"model": model, "messages": messages,
                                "temperature": temperature}

        class _M:
            content = "answer text"

        class _C:
            message = _M()

        class _R:
            choices = [_C()]

        return _R()


class FakeOpenAI:
    def __init__(self):
        self.captured = {}
        self.chat = self
        self.completions = _FakeCompletions(self)


def test_openrouter_text_only():
    fake = FakeOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="m", client=fake)
    out = c.generate("SYS", "USER", images=[])
    assert out == "answer text"
    msgs = fake.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1]["content"] == [{"type": "text", "text": "USER"}]


def test_openrouter_attaches_images_as_data_urls():
    fake = FakeOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="m", client=fake)
    c.generate("SYS", "USER", images=[b"PNGBYTES"])
    content = fake.captured["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "USER"}
    b64 = base64.b64encode(b"PNGBYTES").decode("ascii")
    assert content[1] == {"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}}


def test_make_synth_client_selects_provider():
    class Cfg:
        synth_provider = "openrouter"
        openrouter_api_key = "k"
        openrouter_model = "m"
        google_cloud_project = "p"
        google_cloud_location = "us-central1"
        vertex_model = "gemini-2.5-flash"

    c = make_synth_client(Cfg())
    assert isinstance(c, OpenRouterSynthClient)


def test_make_synth_client_selects_local():
    class Cfg:
        synth_provider = "local"
        local_base_url = "http://localhost:11434/v1"
        local_model = "qwen2.5:7b"

    c = make_synth_client(Cfg())
    assert isinstance(c, LocalSynthClient)
    assert c.base_url == "http://localhost:11434/v1"
    assert c.model == "qwen2.5:7b"


def test_local_is_text_only_even_with_images():
    # Text-only by design: figure images are dropped, the user prompt is sent as a
    # plain string (no image_url parts), citations come from the prompt text.
    fake = FakeOpenAI()
    c = LocalSynthClient(base_url="http://x/v1", model="m", client=fake)
    out = c.generate("SYS", "USER", images=[b"PNGBYTES"])
    assert out == "answer text"
    msgs = fake.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "USER"}
