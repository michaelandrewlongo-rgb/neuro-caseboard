from neuro_caseboard.topic_extract import extract_board_topic


class _FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, system, user, images):
        self.calls.append((system, user, images))
        return self.reply


def test_extract_returns_cleaned_single_line_topic():
    fc = _FakeClient("MCA aneurysm clipping\n")
    topic = extract_board_topic("what structures are at risk clipping an MCA aneurysm?", client=fc)
    assert topic == "MCA aneurysm clipping"
    assert "MCA aneurysm" in fc.calls[0][1]   # the question is passed to the client


def test_extract_falls_back_to_question_on_empty():
    fc = _FakeClient("   ")
    q = "vasospasm management in SAH"
    assert extract_board_topic(q, client=fc) == q


def test_extract_includes_answer_context_when_given():
    fc = _FakeClient("ACDF C5-6")
    extract_board_topic("q?", answer="the disc at C5-6 ...", client=fc)
    assert "Answer (context)" in fc.calls[0][1]
