from caseprep.fact_validation import validate_rendered_fact_consistency


def _schema_with_facts(facts: dict) -> dict:
    return {"case": {"facts": facts}}


def test_validator_flags_known_nihss_rendered_as_missing():
    schema = _schema_with_facts(
        {"nihss": {"key": "nihss", "label": "NIHSS", "value": "18", "status": "known"}}
    )
    markdown = "## Patient-Specific Fact Status\n\n- NIHSS: missing/needs input\n"

    warnings = validate_rendered_fact_consistency(schema, markdown)

    assert warnings == [
        "Fact consistency warning: known NIHSS (18) rendered with missing phrase 'NIHSS: missing/needs input'"
    ]


def test_validator_allows_missing_fact_rendered_as_missing():
    schema = _schema_with_facts(
        {"nihss": {"key": "nihss", "label": "NIHSS", "status": "missing"}}
    )
    markdown = "## Patient-Specific Fact Status\n\n- NIHSS: missing/needs input\n"

    assert validate_rendered_fact_consistency(schema, markdown) == []


def test_validator_flags_known_aspects_with_stale_incomplete_phrase():
    schema = _schema_with_facts(
        {"aspects": {"key": "aspects", "label": "ASPECTS", "value": "7", "status": "known"}}
    )
    markdown = "- ASPECTS numeric score and involved regions: incomplete/needs input.\n"

    warnings = validate_rendered_fact_consistency(schema, markdown)

    assert warnings == [
        "Fact consistency warning: known ASPECTS (7) rendered with missing phrase 'ASPECTS numeric score and involved regions: incomplete/needs input'"
    ]


def test_validator_flags_known_lkw_access_and_perfusion_stale_phrases():
    schema = _schema_with_facts(
        {
            "last_known_well": {
                "key": "last_known_well",
                "label": "Last known well",
                "value": "10h",
                "status": "known",
            },
            "access_route": {
                "key": "access_route",
                "label": "Access route",
                "value": "transfemoral",
                "status": "known",
            },
            "perfusion_selection": {
                "key": "perfusion_selection",
                "label": "Perfusion selection",
                "value": "CT perfusion mismatch",
                "status": "known",
            },
        }
    )
    markdown = "\n".join(
        [
            "- LKW/time window | incomplete/needs input",
            "- Access route: missing/needs input",
            "- Core volume (mL), penumbra/hypoperfusion volume (mL), mismatch ratio, and Tmax/CBF thresholds if CTP used: incomplete/needs input.",
        ]
    )

    warnings = validate_rendered_fact_consistency(schema, markdown)

    assert warnings == [
        "Fact consistency warning: known Last known well (10h) rendered with missing phrase 'LKW/time window | incomplete/needs input'",
        "Fact consistency warning: known Access route (transfemoral) rendered with missing phrase 'Access route: missing/needs input'",
        "Fact consistency warning: known Perfusion selection (CT perfusion mismatch) rendered with missing phrase 'Core volume (mL), penumbra/hypoperfusion volume (mL), mismatch ratio, and Tmax/CBF thresholds if CTP used: incomplete/needs input'",
    ]
