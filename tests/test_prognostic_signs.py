from caseprep.prognostic_signs import (
    prognostic_signs_for_family,
    valid_thrombectomy_pack_ids,
    resolve_pack_refs,
)


def test_thrombectomy_has_favorable_and_unfavorable():
    block = prognostic_signs_for_family("endovascular_thrombectomy")
    assert block is not None
    assert block["favorable"] and block["unfavorable"]


def test_every_indicator_cites_a_real_pack_id():
    block = prognostic_signs_for_family("endovascular_thrombectomy")
    valid = valid_thrombectomy_pack_ids()
    for group in ("favorable", "unfavorable"):
        for entry in block[group]:
            assert entry["indicator"] and entry["detail"]
            assert entry["source_ids"], f"{entry['indicator']} has no source_ids"
            for sid in entry["source_ids"]:
                assert sid in valid, f"{sid} not a thrombectomy pack item id"


def test_unknown_family_returns_none():
    assert prognostic_signs_for_family("spine_acdf") is None


def test_resolve_pack_refs_renders_pmid():
    refs = resolve_pack_refs(["hermes"])
    assert "hermes" in refs.lower()
    assert "26898852" in refs  # HERMES PMID


def test_returned_block_is_isolated_from_registry():
    a = prognostic_signs_for_family("endovascular_thrombectomy")
    a["favorable"][0]["source_ids"].append("MUTANT")
    b = prognostic_signs_for_family("endovascular_thrombectomy")
    assert "MUTANT" not in b["favorable"][0]["source_ids"]
