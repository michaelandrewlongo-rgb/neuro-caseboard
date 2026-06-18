from caseprep.fact_projection import fact_line, has_known_fact, missing_or_confirm_line
from caseprep.facts import CaseFact, FactStatus


def test_has_known_fact_requires_known_status_and_value():
    facts = {
        "nihss": CaseFact("nihss", "NIHSS", "18", FactStatus.KNOWN).to_dict(),
        "lkw": CaseFact("lkw", "LKW", status=FactStatus.MISSING).to_dict(),
    }

    assert has_known_fact(facts, "nihss")
    assert not has_known_fact(facts, "lkw")
    assert not has_known_fact(facts, "aspects")


def test_fact_line_renders_known_value_or_missing_prompt():
    facts = {
        "aspects": CaseFact("aspects", "ASPECTS", "7", FactStatus.KNOWN).to_dict(),
        "access_route": CaseFact("access_route", "Access route", status=FactStatus.MISSING).to_dict(),
    }

    assert fact_line(facts, "aspects") == "ASPECTS: 7"
    assert fact_line(facts, "access_route") == "Access route: missing/needs input"
    assert fact_line(facts, "nihss", label="NIHSS") == "NIHSS: missing/needs input"


def test_missing_or_confirm_line_renders_known_missing_and_confirm_states():
    facts = {
        "balloon_guide": CaseFact("balloon_guide", "Balloon guide", "BGC", FactStatus.CONFIRM).to_dict(),
        "aspiration": CaseFact("aspiration", "Aspiration", "aspiration", FactStatus.KNOWN).to_dict(),
    }

    assert missing_or_confirm_line(facts, "aspiration") == "Aspiration: aspiration"
    assert missing_or_confirm_line(facts, "balloon_guide") == "Balloon guide: confirm BGC"
    assert missing_or_confirm_line(facts, "stent_retriever", label="Stent retriever") == "Stent retriever: missing/needs input"
