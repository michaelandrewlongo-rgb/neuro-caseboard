from neuro_caseboard import briefing_synth as bs


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
