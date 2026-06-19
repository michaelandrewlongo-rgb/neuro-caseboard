"""Hermetic unit tests for standardized PubMed augmentation
(neuro_caseboard/literature/standardize.py), BACKLOG P2 #7. Pure — no network/LLM."""
from dataclasses import dataclass, field

from neuro_caseboard.literature.standardize import Augmentation, standardize_records


@dataclass
class _Rec:
    pmid: str
    pub_types: list = field(default_factory=list)


GUIDE = ["Practice Guideline"]
RCT = ["Randomized Controlled Trial"]
COHORT = ["Cohort Study"]      # tier 2 ("cohort")
CASE = ["Case Reports"]        # tier 4
UNTYPED = ["Journal Article"]  # tier 3


def test_drops_low_tier_padding_and_keeps_quality():
    ranked = [_Rec("1", GUIDE), _Rec("2", RCT), _Rec("3", CASE), _Rec("4", UNTYPED)]
    aug = standardize_records(ranked, k=8)
    assert isinstance(aug, Augmentation)
    kept = {r.pmid for r in aug.records}
    assert kept == {"1", "2"}          # guideline + RCT kept; case-report + untyped dropped
    assert "Limited literature" in aug.note


def test_no_note_when_enough_quality():
    ranked = [_Rec(str(i), RCT) for i in range(8)]
    aug = standardize_records(ranked, k=3)
    assert len(aug.records) == 3 and aug.note == ""


def test_fallback_to_single_most_relevant_when_no_quality():
    ranked = [_Rec("1", CASE), _Rec("2", UNTYPED)]
    aug = standardize_records(ranked, k=8)
    assert [r.pmid for r in aug.records] == ["1"]   # most-relevant single, flagged
    assert "interpret with caution" in aug.note


def test_empty_input_explains_no_literature():
    aug = standardize_records([], k=8)
    assert aug.records == [] and "No relevant literature" in aug.note


def test_relevance_order_is_preserved_among_kept():
    ranked = [_Rec("a", RCT), _Rec("b", GUIDE), _Rec("c", COHORT)]
    aug = standardize_records(ranked, k=8)
    assert [r.pmid for r in aug.records] == ["a", "b", "c"]  # order unchanged, all quality


def test_retrieve_applies_quality_floor_and_sets_note():
    """retrieve drops low-tier padding and records a coverage note. Hermetic fake client."""
    import asyncio
    from neuro_caseboard.literature.retriever import LiteratureRetriever

    class _Client:
        async def search(self, query, *, max_results=25, filter_type=None):
            return (["1", "2", "3"], 3)

        async def summaries(self, pmids):
            pt = {"1": ["Practice Guideline"], "2": ["Case Reports"], "3": ["Journal Article"]}
            return [{"pmid": p, "title": f"T{p}", "source": "J", "pubdate": "2023 Jan",
                     "pub_types": pt[p]} for p in ["1", "2", "3"]]

        async def structured_abstracts(self, pmids):
            return {p: {"Results": "x"} for p in ["1", "2", "3"]}

        async def abstracts(self, pmids):
            return {p: "abstract" for p in ["1", "2", "3"]}

    r = LiteratureRetriever(_Client(), k=8, recency_years=7)
    recs = asyncio.run(r.retrieve("subdural hematoma MMA embolization", current_year=2024))
    assert [x.pmid for x in recs] == ["1"]        # only the guideline clears the floor
    assert "Limited literature" in r.last_coverage_note
