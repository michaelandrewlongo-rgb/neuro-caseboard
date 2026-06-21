from neuro_caseboard.woven_synth import synthesize_woven, WovenSynthesis, WOVEN_SYSTEM
from neuro_caseboard.literature.retriever import LiteratureRecord
from neuro_core.index import Hit


class _Spy:
    def __init__(self, reply="Woven answer [1] and recent trial [L1]."):
        self.reply = reply
        self.system = None
        self.user = None
        self.images = None

    def generate(self, system, user, images):
        self.system, self.user, self.images = system, user, images
        return self.reply


def _hit(n):
    return Hit(id=str(n), book="Greenberg", chapter="Ch", page=n, text=f"passage {n}")


def _rec(pmid="111"):
    return LiteratureRecord(pmid=pmid, title="DISTAL trial", journal="NEJM", year=2024,
                            doi="10/x", url="u", abstract="distal occlusion thrombectomy",
                            sections={}, pub_types=["Randomized Controlled Trial"])


def test_woven_includes_both_blocks_and_builds_citations():
    spy = _Spy()
    out = synthesize_woven("q", [_hit(1), _hit(2)], [], [], [_rec("111")], spy)
    assert isinstance(out, WovenSynthesis)
    assert out.answer == "Woven answer [1] and recent trial [L1]."
    assert "Textbook passages:" in spy.user
    assert "[1] Greenberg, Ch, p.1" in spy.user
    assert "Contemporary studies:" in spy.user
    assert "[L1] DISTAL trial" in spy.user
    assert [c.n for c in out.citations] == [1, 2]
    assert [r.pmid for r in out.records] == ["111"]
    assert spy.system is WOVEN_SYSTEM


def test_woven_without_records_omits_studies_block():
    spy = _Spy(reply="Textbook only [1].")
    out = synthesize_woven("q", [_hit(1)], [], [], [], spy)
    assert "Contemporary studies:" not in spy.user
    assert out.records == []
    assert [c.n for c in out.citations] == [1]


def test_woven_passes_images_and_variant_directive():
    spy = _Spy()
    synthesize_woven("q", [_hit(1)], [], [b"PNG"], [_rec()], spy,
                     variant_directive="Answer for the variant 'X' ONLY.")
    assert spy.images == [b"PNG"]
    assert "Answer for the variant 'X' ONLY." in spy.user


def test_woven_prompt_contract_strings():
    # The prompt must keep namespaces distinct, define the textbook-silent flag, and
    # emit the shared REFUSAL verbatim so is_refusal() matches downstream.
    from neuro_core.synthesize import REFUSAL
    assert "[L#]" in WOVEN_SYSTEM and "[n]" in WOVEN_SYSTEM
    assert REFUSAL in WOVEN_SYSTEM
    assert "textbook corpus did not cover" in WOVEN_SYSTEM.lower()
