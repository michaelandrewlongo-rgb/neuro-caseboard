import base64

import pytest

from neuro_core.synth_clients import (
    LocalSynthClient,
    OpenRouterSynthClient,
    make_synth_client,
    make_analyze_client,
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


def test_make_analyze_client_uses_separate_model():
    # Disambiguation runs its own (cheaper/faster) model, distinct from synthesis.
    class Cfg:
        synth_provider = "openrouter"
        analyze_provider = "openrouter"
        analyze_model = "google/gemini-3.1-flash-lite"
        openrouter_api_key = "k"
        openrouter_model = "z-ai/glm-5.2"
        google_cloud_project = "p"
        google_cloud_location = "us-central1"
        vertex_model = "gemini-2.5-pro"

    c = make_analyze_client(Cfg())
    assert isinstance(c, OpenRouterSynthClient)
    assert c.model == "google/gemini-3.1-flash-lite"  # not the synthesis model


def test_make_analyze_client_falls_back_to_synth_when_unset():
    # Empty ANALYZE_MODEL -> reuse the synthesis client (historical single-client behavior).
    class Cfg:
        synth_provider = "openrouter"
        analyze_provider = ""
        analyze_model = ""
        openrouter_api_key = "k"
        openrouter_model = "z-ai/glm-5.2"

    c = make_analyze_client(Cfg())
    assert isinstance(c, OpenRouterSynthClient)
    assert c.model == "z-ai/glm-5.2"  # same as synthesis


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


def _image_input_404():
    # Mirrors the real OpenRouter rejection for a text-only model (e.g. z-ai/glm-5.2):
    #   404 - {'error': {'message': 'No endpoints found that support image input'}}
    # The fix detects by message, so a same-message carrier exercises the same path.
    # Use the real openai.NotFoundError when openai is installed (local dev); fall back
    # to a generic exception in the required `.[dev]` CI env where openai is absent
    # (openai is an optional extra — never import it at test-module top level).
    msg = ("Error code: 404 - {'error': {'message': 'No endpoints found that "
           "support image input', 'code': 404}}")
    try:
        import httpx
        import openai
        resp = httpx.Response(404, request=httpx.Request("POST", "http://x/v1"))
        return openai.NotFoundError(msg, response=resp, body=None)
    except Exception:
        return RuntimeError(msg)


class _FakeImageRejectingCompletions:
    """create() rejects any request carrying image_url parts (text-only model),
    succeeds on text-only requests."""

    def __init__(self, parent):
        self.parent = parent

    def create(self, model, messages, temperature):
        self.parent.calls += 1
        content = messages[1]["content"]
        has_image = isinstance(content, list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in content)
        if has_image:
            raise _image_input_404()
        self.parent.last_content = content

        class _M:
            content = "answer text"

        class _C:
            message = _M()

        class _R:
            choices = [_C()]

        return _R()


class FakeImageRejectingOpenAI:
    def __init__(self):
        self.calls = 0
        self.last_content = None
        self.chat = self
        self.completions = _FakeImageRejectingCompletions(self)


class _FakeRaisingCompletions:
    def __init__(self, exc):
        self.exc = exc

    def create(self, model, messages, temperature):
        raise self.exc


class FakeRaisingOpenAI:
    def __init__(self, exc):
        self.chat = self
        self.completions = _FakeRaisingCompletions(exc)


def test_openrouter_retries_text_only_when_model_rejects_images():
    # An *unknown* text-only model (not in _TEXT_ONLY_MODEL_HINTS) 404s on figure images.
    # It starts optimistic, so the client must drop the images and retry text-only so
    # figure-bearing Ask queries still answer (captions are already in the prompt text).
    # (Known text-only ids like z-ai/glm-5.2 start text-only and never make this round-trip.)
    fake = FakeImageRejectingOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="some/unknown-text-model", client=fake)
    out = c.generate("SYS", "USER", images=[b"PNGBYTES"])
    assert out == "answer text"
    assert fake.calls == 2  # first attempt with image (rejected), retry text-only
    assert fake.last_content == [{"type": "text", "text": "USER"}]


def test_openrouter_skips_images_after_image_rejection():
    # Once a model is learned text-only at runtime, later calls must not re-send images
    # (no wasted failing round-trip per query).
    fake = FakeImageRejectingOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="some/unknown-text-model", client=fake)
    c.generate("SYS", "USER", images=[b"PNG"])  # learns: text-only (2 calls)
    fake.calls = 0
    c.generate("SYS", "USER2", images=[b"PNG"])  # must skip image upfront -> 1 call
    assert fake.calls == 1
    assert fake.last_content == [{"type": "text", "text": "USER2"}]


def test_glm_starts_text_only_no_wasted_image_roundtrip():
    # Known text-only model: generate() must skip images on the very first call (1 call,
    # no rejection round-trip) — the streaming path depends on this default.
    fake = FakeImageRejectingOpenAI()
    c = OpenRouterSynthClient(api_key="k", model="z-ai/glm-5.2", client=fake)
    assert c._supports_images is False
    out = c.generate("SYS", "USER", images=[b"PNGBYTES"])
    assert out == "answer text"
    assert fake.calls == 1
    assert fake.last_content == [{"type": "text", "text": "USER"}]


def test_openrouter_propagates_non_image_errors():
    # The retry is scoped to image-input rejections only; unrelated errors propagate.
    fake = FakeRaisingOpenAI(RuntimeError("boom"))
    c = OpenRouterSynthClient(api_key="k", model="m", client=fake)
    with pytest.raises(RuntimeError):
        c.generate("SYS", "USER", images=[b"PNG"])
