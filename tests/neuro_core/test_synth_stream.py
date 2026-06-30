"""generate_stream yields deltas that concatenate to the full answer."""
from neuro_core.synth_clients import OpenRouterSynthClient, LocalSynthClient, VertexSynthClient


class _FakeDelta:
    def __init__(self, content): self.content = content
class _FakeChoice:
    def __init__(self, content): self.delta = _FakeDelta(content)
class _FakeChunk:
    def __init__(self, content): self.choices = [_FakeChoice(content)]


class _FakeOpenAI:
    """Stands in for the openai client; records the create() kwargs and returns a chunk stream."""
    def __init__(self, parts): self._parts = parts; self.kwargs = None
    @property
    def chat(self): return self
    @property
    def completions(self): return self
    def create(self, **kwargs):
        self.kwargs = kwargs
        return iter([_FakeChunk(p) for p in self._parts] + [_FakeChunk(None)])


def test_openrouter_generate_stream_concats():
    fake = _FakeOpenAI(["Hel", "lo ", "world"])
    c = OpenRouterSynthClient(api_key="x", model="m", client=fake)
    out = list(c.generate_stream("sys", "user", []))
    assert "".join(out) == "Hello world"
    assert fake.kwargs["stream"] is True          # actually streamed, not a single shot
    assert fake.kwargs["model"] == "m"


def test_glm_defaults_text_only_so_stream_omits_images():
    # glm-5.x has no image endpoint. generate_stream has no image-retry, so sending figure
    # images makes it throw and silently fall back to blocking synthesis — killing token
    # streaming on every figure-bearing query. So glm must start text-only up front.
    fake = _FakeOpenAI(["x"])
    c = OpenRouterSynthClient(api_key="k", model="z-ai/glm-5.2", client=fake)
    assert c._supports_images is False
    list(c.generate_stream("sys", "user", [b"IMAGEBYTES"]))
    content = fake.kwargs["messages"][1]["content"]
    assert all(part.get("type") != "image_url" for part in content)  # no images leak to glm


def test_vision_model_defaults_to_sending_images():
    # Non-text-only models keep the optimistic default (+ runtime learn-down on rejection).
    fake = _FakeOpenAI(["x"])
    c = OpenRouterSynthClient(api_key="k", model="anthropic/claude-3.5-sonnet", client=fake)
    assert c._supports_images is True
    list(c.generate_stream("sys", "user", [b"IMAGEBYTES"]))
    content = fake.kwargs["messages"][1]["content"]
    assert any(part.get("type") == "image_url" for part in content)


def test_local_generate_stream_is_text_only():
    fake = _FakeOpenAI(["a", "b"])
    c = LocalSynthClient(base_url="http://local", model="m", client=fake)
    out = list(c.generate_stream("sys", "user", [b"IMAGEBYTES"]))
    assert "".join(out) == "ab"
    # text-only: the user message is a plain string, no image parts leak to a local model
    assert fake.kwargs["messages"][1]["content"] == "user"


def test_vertex_generate_stream_concats():
    import pytest
    # google-genai is an optional extra (the `[vertex]` SDK), absent from the required `.[dev]`
    # CI env; generate_stream builds real types.Part objects, so skip where the SDK is missing.
    pytest.importorskip("google.genai")

    class _Chunk:
        def __init__(self, t): self.text = t
    class _Models:
        def generate_content_stream(self, **kwargs):
            return iter([_Chunk("foo"), _Chunk(""), _Chunk("bar"), _Chunk(None)])
    class _FakeGenai:
        models = _Models()
    c = VertexSynthClient(project="p", location="l", model="m", client=_FakeGenai())
    out = list(c.generate_stream("sys", "user", []))
    assert "".join(out) == "foobar"
