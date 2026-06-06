# tests/test_synthesize.py
from engine.synthesize import synthesize, SYSTEM_PROMPT, _format_passages
from engine.index import Hit


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeClient:
    def __init__(self):
        self.captured = {}
        self.chat = self  # so client.chat.completions.create resolves
        self.completions = self

    def create(self, model, messages, temperature):
        self.captured = {"model": model, "messages": messages,
                         "temperature": temperature}
        return FakeCompletion("ICP is 5-15 mmHg [1].")


def _hit():
    return Hit(id="x", book="NeuroICU", chapter="Pressure", page=10,
               text="normal icp is 5 to 15 mmHg")


def test_synthesize_builds_prompt_and_citations():
    client = FakeClient()
    out = synthesize("normal icp?", [_hit()], client, "anthropic/claude-sonnet-4.6")

    assert out.answer == "ICP is 5-15 mmHg [1]."
    assert client.captured["model"] == "anthropic/claude-sonnet-4.6"
    sys_msg = client.captured["messages"][0]
    user_msg = client.captured["messages"][1]
    assert sys_msg["content"] == SYSTEM_PROMPT
    assert "[1] NeuroICU, Pressure, p.10" in user_msg["content"]
    assert "normal icp is 5 to 15 mmHg" in user_msg["content"]

    assert len(out.citations) == 1
    assert out.citations[0].n == 1
    assert out.citations[0].book == "NeuroICU"
    assert out.citations[0].page == 10


def test_synthesize_no_hits_is_empty_refusal_path():
    # The refusal path the spec requires: with no retrieved passages, the
    # passages section is empty and no citations are produced. (The system
    # prompt instructs the model to answer "Not found in the provided sources.")
    assert _format_passages([]) == ""
    client = FakeClient()
    out = synthesize("obscure question?", [], client, "anthropic/claude-sonnet-4.6")
    assert out.citations == []
    user_msg = client.captured["messages"][1]
    assert user_msg["content"].rstrip().endswith("Passages:")
