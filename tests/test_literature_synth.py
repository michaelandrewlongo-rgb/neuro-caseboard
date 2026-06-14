from neuro_caseboard.literature.synth import (
    synthesize_literature, is_lit_refusal, LIT_REFUSAL,
)
from neuro_caseboard.literature.retriever import LiteratureRecord


def _rec(pmid, title):
    return LiteratureRecord(pmid=pmid, title=title, journal="Stroke", year=2024,
                            doi="d", url="u", abstract=f"abstract {pmid}",
                            sections={}, pub_types=["Review"])


class _FakeSynth:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, system, user, images):
        self.calls.append((system, user, images))
        return self.reply


def test_synthesizes_narrative_and_keeps_records():
    sc = _FakeSynth("EVT has expanded to distal vessels [L1]. Bridging shifts [L2].")
    out = synthesize_literature("distal MCA", [_rec("1", "A"), _rec("2", "B")], sc)
    assert out is not None
    assert "[L1]" in out.narrative
    assert [r.pmid for r in out.records] == ["1", "2"]
    # text-only: images must be empty, and each study appears in the prompt
    assert sc.calls[0][2] == []
    assert "[L1]" in sc.calls[0][1] and "abstract 1" in sc.calls[0][1]


def test_refusal_reply_yields_none():
    sc = _FakeSynth(LIT_REFUSAL)
    assert synthesize_literature("q", [_rec("1", "A")], sc) is None


def test_empty_records_yields_none():
    sc = _FakeSynth("anything")
    assert synthesize_literature("q", [], sc) is None
    assert sc.calls == []  # no model call when there is nothing to synthesize


def test_is_lit_refusal_normalizes():
    assert is_lit_refusal("  No relevant recent literature found.  ")
    assert not is_lit_refusal("Recent RCTs show...")
