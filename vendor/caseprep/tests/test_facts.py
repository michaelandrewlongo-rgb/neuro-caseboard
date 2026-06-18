from caseprep.facts import CaseFact, FactStatus, facts_to_dict, fact_value


def test_case_fact_serializes_status_and_metadata():
    fact = CaseFact(
        key="nihss",
        label="NIHSS",
        value="18",
        status=FactStatus.KNOWN,
        source="extracted",
        confidence=0.95,
        span="NIHSS 18",
        notes="deterministic parser",
    )

    assert fact.to_dict() == {
        "key": "nihss",
        "label": "NIHSS",
        "value": "18",
        "status": "known",
        "source": "extracted",
        "confidence": 0.95,
        "span": "NIHSS 18",
        "notes": "deterministic parser",
    }
    assert facts_to_dict([fact])["nihss"] == fact.to_dict()
    assert fact_value([fact], "nihss") == "18"


def test_fact_value_returns_none_for_missing_or_absent_fact():
    missing = CaseFact(
        key="last_known_well",
        label="Last known well",
        status=FactStatus.MISSING,
    )

    assert fact_value([missing], "last_known_well") is None
    assert fact_value([missing], "nihss") is None


def test_facts_to_dict_preserves_outer_mapping_key_when_inner_key_missing():
    facts = {
        "nihss": {
            "label": "NIHSS",
            "value": "18",
            "status": FactStatus.KNOWN,
        }
    }

    serialized = facts_to_dict(facts)

    assert serialized["nihss"] == {
        "key": "nihss",
        "label": "NIHSS",
        "value": "18",
        "status": "known",
    }
