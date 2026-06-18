"""Tests for deterministic query enrichment before external retrieval."""

from __future__ import annotations

import json

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.query_enrichment import PriorEnrichment, enrich_case_query


def test_prior_enrichment_to_dict_includes_empty_metadata():
    serialized = PriorEnrichment().to_dict()

    assert serialized["metadata"] == {}
    json.dumps(serialized)


def test_enrich_case_query_returns_json_serializable_m1_plan():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")

    json.dumps(plan)
    assert plan["case"]["laterality"]["value"] == "right"
    assert plan["procedure_family"] == "endovascular_thrombectomy"
    assert plan["profile"] == "vascular"
    assert plan["retrieval_strategy"] == "deterministic_enrichment"
    assert plan["expansion_terms"]
    assert plan["queries"]
    assert all(query["id"] for query in plan["queries"])
    assert all(query["query"] for query in plan["queries"] if query["retriever"] == "pubmed")
    assert all(query["query_spec"] for query in plan["queries"] if query["retriever"] == "pubmed")
    assert all(query["case_fact_policy"] for query in plan["queries"])
    assert all(query["provenance"] for query in plan["queries"])


def test_m1_thrombectomy_expands_anatomy_technique_and_outcomes():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")
    aliases = {
        alias.casefold()
        for term in plan["expansion_terms"]
        for alias in term["aliases"]
    }

    assert "m1 occlusion" in aliases
    assert "middle cerebral artery occlusion" in aliases
    assert "mca occlusion" in aliases
    assert "large vessel occlusion" in aliases
    assert "endovascular thrombectomy" in aliases
    assert "stent retriever" in aliases
    assert "aspiration thrombectomy" in aliases
    assert "mtici" in aliases
    assert "modified rankin scale" in aliases
    assert "nihss" in aliases
    assert "acute ischemic stroke" in aliases
    assert "anterior circulation lvo" in aliases
    assert "early window" in aliases
    assert "late window" in aliases
    assert "extended window" in aliases
    assert "6-24 hours" in aliases
    assert "ct angiography" in aliases
    assert "ct perfusion" in aliases
    assert "aspects" in aliases

    concept_types = {term["concept_type"] for term in plan["expansion_terms"]}
    assert {"population", "temporal_window", "imaging_modality"} <= concept_types


def test_broad_pubmed_queries_use_fielded_terms_date_filter_and_laterality_policy():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")
    outcomes = next(query for query in plan["queries"] if query["id"] == "pubmed_outcomes")
    query = outcomes["query"].casefold()

    assert plan["case"]["laterality"]["value"] == "right"
    assert outcomes["case_fact_policy"]["laterality"] == "strip_for_broad_literature_search"
    assert "right" not in query
    assert "[mesh]" in query
    assert "[tiab]" in query
    assert "date - publication" in query
    assert outcomes["query_spec"]["date_filter"] == "2015/01/01:3000/12/31"
    assert outcomes["query_spec"]["omitted_terms"] == []
    assert not any("laterality preserved" in warning.casefold() for warning in plan["warnings"])


def test_pubmed_query_truncation_is_explicit_when_aliases_exceed_bound():
    from caseprep.query_enrichment import ExpansionProvenance, ExpansionTerm, PriorEnrichment

    class VerbosePrior:
        def enrich(self, case, family, profile):
            return PriorEnrichment(
                expansion_terms=(
                    ExpansionTerm(
                        canonical="verbose outcome aliases",
                        aliases=tuple(f"extra outcome term {idx}" for idx in range(10)),
                        concept_type="outcome",
                        confidence=0.5,
                        provenance=(ExpansionProvenance(source="fake_prior"),),
                    ),
                )
            )

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        neurosurgery_adapter=VerbosePrior(),
    )
    outcomes = next(query for query in plan["queries"] if query["id"] == "pubmed_outcomes")

    assert outcomes["query_spec"]["omitted_terms"]
    assert any("omitted" in warning.casefold() for warning in outcomes["warnings"])


def test_degraded_unknown_case_uses_baseline_query_with_warning():
    case = parse_case_input("vestibular schwannoma")
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="skull_base")

    assert plan["case"]["degraded"] is True
    assert plan["procedure_family"] in (None, plan["case"]["procedure_family"]["value"])
    assert [query["id"] for query in plan["queries"]] == ["pubmed_baseline"]
    assert plan["queries"][0]["query"] == '"vestibular schwannoma"[tiab]'
    assert plan["queries"][0]["query_spec"]["tiab_terms"] == ["vestibular schwannoma"]
    assert any("generic baseline" in warning.casefold() for warning in plan["warnings"])


def test_m1_thrombectomy_includes_curated_landmark_seeds_without_corpus_adapter():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(case, family, profile="vascular")
    seeds_by_id = {seed["id"]: seed for seed in plan["seed_sources"]}

    for seed_id in ["mr_clean", "escape", "extend_ia", "swift_prime", "revascat", "hermes"]:
        assert seed_id in seeds_by_id
        assert seeds_by_id[seed_id]["pmid"]
        assert seeds_by_id[seed_id]["provenance"]
        assert seeds_by_id[seed_id]["provenance"][0]["source"] == "caseprep.evidence_packs.thrombectomy"

    assert seeds_by_id["mr_clean"]["pmid"] == "25517348"
    assert seeds_by_id["hermes"]["pmid"] == "26898852"


def test_seed_sources_deduplicate_by_identifier_and_merge_provenance():
    from caseprep.query_enrichment import ExpansionProvenance, PriorEnrichment, SeedSource

    class DuplicateCorpusSeedPrior:
        def enrich(self, case, family, profile):
            return PriorEnrichment(
                seed_sources=(
                    SeedSource(
                        id="corpus_mr_clean_duplicate",
                        title_hint="MR CLEAN duplicate from corpus",
                        pmid=None,
                        doi="10.1056/NEJMoa1411587",
                        provenance=(
                            ExpansionProvenance(source="local_corpus", field_path="identifiers.doi"),
                        ),
                    ),
                )
            )

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        neurosurgery_adapter=DuplicateCorpusSeedPrior(),
    )
    mr_clean = [seed for seed in plan["seed_sources"] if seed["pmid"] == "25517348"]
    mr_clean_by_doi = [seed for seed in plan["seed_sources"] if seed["doi"] == "10.1056/NEJMoa1411587"]

    assert len(mr_clean) == 1
    assert len(mr_clean_by_doi) == 1
    assert {prov["source"] for prov in mr_clean[0]["provenance"]} == {
        "caseprep.evidence_packs.thrombectomy",
        "local_corpus",
    }


def test_seed_source_merge_coalesces_multi_identifier_bridge_duplicates():
    from caseprep.query_enrichment import ExpansionProvenance, SeedSource, _merge_seed_sources

    pmid_seed = SeedSource(
        id="pmid_seed",
        title_hint="PMID-only seed",
        pmid="12345678",
        provenance=(ExpansionProvenance(source="pmid_source"),),
    )
    doi_seed = SeedSource(
        id="doi_seed",
        title_hint="DOI-only seed",
        doi="10.1000/bridge.seed",
        provenance=(ExpansionProvenance(source="doi_source"),),
    )
    bridge_seed = SeedSource(
        id="bridge_seed",
        title_hint="Bridge seed with both identifiers",
        pmid="12345678",
        doi="10.1000/bridge.seed",
        pmcid="PMC123456",
        work_id="w_bridge",
        provenance=(ExpansionProvenance(source="bridge_source"),),
    )

    merged = _merge_seed_sources((pmid_seed, doi_seed), (bridge_seed,))

    assert len(merged) == 1
    assert merged[0].id == "pmid_seed"
    assert merged[0].pmid == "12345678"
    assert merged[0].doi == "10.1000/bridge.seed"
    assert merged[0].pmcid == "PMC123456"
    assert merged[0].work_id == "w_bridge"
    assert [provenance.source for provenance in merged[0].provenance] == [
        "pmid_source",
        "doi_source",
        "bridge_source",
    ]


def test_neurosurgery_adapter_terms_are_merged_with_fixture_terms():
    from caseprep.query_enrichment import ExpansionProvenance, ExpansionTerm, PriorEnrichment

    class FakePrior:
        def enrich(self, case, family, profile):
            return PriorEnrichment(
                expansion_terms=(
                    ExpansionTerm(
                        canonical="local corpus first pass effect",
                        aliases=("first pass effect", "first pass reperfusion"),
                        concept_type="outcome",
                        confidence=0.88,
                        provenance=(
                            ExpansionProvenance(
                                source="fake_nsgy_db",
                                field_path="subjects.value",
                                matched_value="first pass effect",
                            ),
                        ),
                    ),
                ),
                subdomain_hints=("stroke_thrombectomy",),
                warnings=("fake prior used for test",),
            )

    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    family = select_procedure_family(case)

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        neurosurgery_adapter=FakePrior(),
    )

    assert any(
        term["canonical"] == "local corpus first pass effect"
        and term["provenance"][0]["source"] == "fake_nsgy_db"
        for term in plan["expansion_terms"]
    )
    assert "stroke_thrombectomy" in plan["prior_enrichment"]["subdomain_hints"]
    assert any("fake prior" in warning for warning in plan["warnings"])
