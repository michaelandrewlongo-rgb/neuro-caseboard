from neuro_caseboard import briefing_synth as bs
from neuro_caseboard.briefing_model import (
    BriefingSection, DecisionAlgorithm, TreatmentModality,
    SpineEquipment, EndovascularEquipment,
)


class FakeRec:
    def __init__(self, text, citation, book="Youmans", page=10):
        self.text = text
        self.metadata = {"citation": citation, "book": book, "page": page}


class FakeRetriever:
    """Returns 1 unique record per query so the packet has stable content."""
    def __init__(self):
        self.calls = []
    def retrieve(self, query, top_n=6):
        self.calls.append(query)
        return [FakeRec(f"passage about {query[:20]}", f"Youmans p.{len(self.calls)}",
                        page=len(self.calls))]


class FakeCase:
    pathology = "ACoA aneurysm"
    procedure = "microsurgical clipping"
    def to_topic(self):
        return "ACoA aneurysm clipping"


class FakeDossier:
    sections = []  # no literature attached in this test


def test_gather_issues_one_query_per_section_and_numbers_sources():
    r = FakeRetriever()
    packet = bs.gather_briefing_evidence(FakeCase(), FakeDossier(), r)
    # one intent query per briefing section (7)
    assert len(r.calls) == len(bs.SECTION_KEYS)
    # textbook sources are numbered T1.. in order, deduped by citation
    ids = [t["ref_id"] for t in packet.textbook]
    assert ids == [f"T{i+1}" for i in range(len(ids))]
    assert "T1" in packet.prompt_block


def test_gather_dedups_identical_citations():
    class DupRetriever:
        def retrieve(self, query, top_n=6):
            return [FakeRec("same", "Youmans p.5", page=5)]
    packet = bs.gather_briefing_evidence(FakeCase(), FakeDossier(), DupRetriever())
    assert len(packet.textbook) == 1  # all 7 queries returned the same citation


def test_parse_prose_section_priority_and_refs():
    txt = ("[critical] Secure the aneurysm early {T1, L2}\n"
           "[high] Counsel on vasospasm risk {T3}\n"
           "[optional] Consider lumbar drain {verify}\n"
           "garbage line with no tag\n")
    sec = bs.parse_prose_section("risks", "Risks", txt)
    assert isinstance(sec, BriefingSection) and sec.key == "risks"
    assert [i.priority for i in sec.items] == ["critical", "high", "optional"]
    assert sec.items[0].source_refs == ["T1", "L2"]
    assert sec.items[2].unsupported is True  # {verify} → unsupported


def test_parse_algorithm_nodes_and_edges():
    txt = ("intro prose ignored\n"
           "---ALGORITHM---\n"
           "N1 | decision | Ruptured?\n"
           "N2 | action | Secure within 72h\n"
           "N1 -> N2 | yes\n")
    algo = bs.parse_algorithm(txt)
    assert isinstance(algo, DecisionAlgorithm)
    assert [n.id for n in algo.nodes] == ["N1", "N2"]
    assert algo.edges[0].src == "N1" and algo.edges[0].condition == "yes"


def test_parse_modalities_blocks():
    txt = ("### Microsurgical clipping\n"
           "role: durable occlusion\n"
           "advantages: durable; treats wide-neck\n"
           "limitations: invasive\n"
           "preferred: yes\n"
           "refs: T1, L2\n"
           "### Endovascular coiling\n"
           "role: less invasive\n"
           "preferred: no\n")
    mods = bs.parse_modalities(txt)
    assert [m.name for m in mods] == ["Microsurgical clipping", "Endovascular coiling"]
    assert mods[0].advantages == ["durable", "treats wide-neck"]
    assert mods[0].preferred is True and mods[1].preferred is False
    assert mods[0].source_refs == ["T1", "L2"]


def test_parse_equipment_selects_schema_by_subspecialty():
    txt = ("access_strategy: transfemoral; radial backup\n"
           "devices: flow diverter; coils\n"
           "refs: T2\n")
    eq = bs.parse_equipment(txt, "endovascular")
    assert isinstance(eq, EndovascularEquipment)
    assert eq.access_strategy == ["transfemoral", "radial backup"]
    assert eq.source_refs == ["T2"]
    # spine fields on a spine schema
    eq2 = bs.parse_equipment("cage_class_sizing: PEEK 6mm\n", "spine")
    assert isinstance(eq2, SpineEquipment) and eq2.cage_class_sizing == ["PEEK 6mm"]
