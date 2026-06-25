from neuro_caseboard import briefing_figures as bf


class FRec:
    def __init__(self, path, cap="cap", cite="Youmans p.1", score=0.9):
        self.metadata = {"figure_path": path, "caption": cap, "citation": cite,
                         "book": "Youmans", "page": 1, "score": score}
    @property
    def text(self):
        return self.metadata["caption"]


class FigRetriever:
    """12 unique plates spread across the 4 intents (3 each)."""
    def retrieve(self, query, topic="", top_n=8):
        # Map query back to intent name by checking which keyword is present
        intent = "unknown"
        if "pathology" in query:
            intent = "pathology"
        elif "anatomy" in query:
            intent = "anatomy"
        elif "technique" in query:
            intent = "technique"
        elif "device" in query:
            intent = "device"
        return [FRec(f"/figs/{intent}_{i}.png", cap=f"{intent} {i}") for i in range(3)]


class FakeCase:
    pathology = "ACoA aneurysm"
    def to_topic(self):
        return "ACoA aneurysm clipping"


def test_selects_up_to_ten_unique_and_records_intent():
    figs, reason = bf.select_briefing_figures(FakeCase(), FigRetriever())
    assert 5 <= len(figs) <= 10
    assert reason == ""
    assert len({f.image_path for f in figs}) == len(figs)        # all unique
    assert all(f.intent in bf.FIGURE_INTENTS for f in figs)       # intent recorded
    assert all(f.fig_id.startswith("BF") for f in figs)


def test_dedup_and_unavailable_and_insufficiency():
    class DupRetriever:
        def retrieve(self, query, topic="", top_n=8):
            return [FRec("/figs/same.png")]   # every intent returns the same plate
    figs, reason = bf.select_briefing_figures(
        FakeCase(), DupRetriever(), image_available=lambda p: True)
    assert len(figs) == 1 and reason != ""    # <5 → explicit insufficiency reason

    # off-target / unavailable images are rejected before counting
    figs2, _ = bf.select_briefing_figures(
        FakeCase(), FigRetriever(), image_available=lambda p: "pathology" not in p)
    assert all("pathology" not in f.image_path for f in figs2)


def test_no_retriever_returns_empty_with_reason():
    figs, reason = bf.select_briefing_figures(FakeCase(), None)
    assert figs == [] and reason
