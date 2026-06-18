"""Contract tests for local SQLite corpus priors used by query enrichment."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.query_enrichment import PriorEnrichment, enrich_case_query
from caseprep.retrievers.corpus_prior import NeurosurgeryCorpusPrior

_ALLOWED_CONCEPT_TYPES = {
    "procedure",
    "anatomy",
    "pathology",
    "approach",
    "outcome",
    "complication",
    "device",
    "study_design",
    "population",
    "temporal_window",
    "imaging_modality",
}


def _create_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE works(
                id TEXT PRIMARY KEY,
                title TEXT,
                abstract TEXT,
                pub_year INTEGER,
                study_design TEXT,
                evidence_tier TEXT,
                citation_count INTEGER
            );
            CREATE TABLE subdomain_assignments(work_id TEXT, subdomain_id TEXT);
            CREATE TABLE identifiers(work_id TEXT, scheme TEXT, value TEXT);
            CREATE TABLE subjects(id INTEGER PRIMARY KEY, scheme TEXT, value TEXT);
            CREATE TABLE work_subjects(work_id TEXT, subject_id INTEGER);
            """
        )


def _insert_work(
    db_path: Path,
    *,
    work_id: str,
    title: str,
    abstract: str,
    pub_year: int,
    study_design: str,
    evidence_tier: str,
    citation_count: int,
    subdomain: str,
    identifiers: dict[str, str],
    subjects: list[tuple[str, str]],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO works(id, title, abstract, pub_year, study_design, evidence_tier, citation_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (work_id, title, abstract, pub_year, study_design, evidence_tier, citation_count),
        )
        conn.execute(
            "INSERT INTO subdomain_assignments(work_id, subdomain_id) VALUES (?, ?)",
            (work_id, subdomain),
        )
        conn.executemany(
            "INSERT INTO identifiers(work_id, scheme, value) VALUES (?, ?, ?)",
            [(work_id, scheme, value) for scheme, value in identifiers.items()],
        )
        for scheme, value in subjects:
            cursor = conn.execute(
                "INSERT INTO subjects(scheme, value) VALUES (?, ?)",
                (scheme, value),
            )
            conn.execute(
                "INSERT INTO work_subjects(work_id, subject_id) VALUES (?, ?)",
                (work_id, cursor.lastrowid),
            )


def _fixture_db(
    tmp_path: Path, *, include_aneurysm: bool = False, include_unidentified: bool = False
) -> Path:
    db_path = tmp_path / "nsgy_corpus_fixture.sqlite"
    _create_schema(db_path)
    _insert_work(
        db_path,
        work_id="w_mr_clean_like",
        title="Randomized trial of mechanical thrombectomy for anterior-circulation stroke",
        abstract=(
            "Patients with acute ischemic stroke, proximal large vessel occlusion, "
            "M1 middle cerebral artery occlusion, and MCA occlusion were treated "
            "with endovascular thrombectomy using stent retriever or aspiration."
        ),
        pub_year=2015,
        study_design="randomized controlled trial",
        evidence_tier="high",
        citation_count=4800,
        subdomain="stroke_thrombectomy",
        identifiers={"pmid": "25517348", "doi": "10.1056/NEJMoa1411587"},
        subjects=[
            ("mesh", "Thrombectomy"),
            ("keyword", "mechanical thrombectomy"),
            ("keyword", "endovascular thrombectomy"),
            ("keyword", "large vessel occlusion"),
            ("keyword", "M1 occlusion"),
            ("keyword", "middle cerebral artery occlusion"),
            ("keyword", "MCA occlusion"),
            ("keyword", "stent retriever"),
        ],
    )
    _insert_work(
        db_path,
        work_id="w_thrombectomy_outcomes",
        title="First pass reperfusion after thrombectomy for large vessel occlusion",
        abstract="mTICI reperfusion and modified Rankin Scale outcomes after thrombectomy.",
        pub_year=2020,
        study_design="cohort study",
        evidence_tier="moderate",
        citation_count=250,
        subdomain="stroke_thrombectomy",
        identifiers={"pmid": "33333333"},
        subjects=[
            ("keyword", "first pass effect"),
            ("keyword", "mTICI"),
            ("keyword", "modified Rankin Scale"),
        ],
    )
    if include_aneurysm:
        _insert_work(
            db_path,
            work_id="w_flow_diversion",
            title="Flow diversion for intracranial aneurysm treatment",
            abstract=(
                "High citation aneurysm series describing flow diverter treatment "
                "for ruptured and unruptured MCA aneurysm cohorts."
            ),
            pub_year=2018,
            study_design="systematic review",
            evidence_tier="high",
            citation_count=5200,
            subdomain="aneurysm_sah",
            identifiers={"pmid": "29999999", "doi": "10.1000/flow.diverter"},
            subjects=[
                ("keyword", "intracranial aneurysm"),
                ("keyword", "MCA aneurysm"),
                ("keyword", "flow diverter"),
                ("keyword", "flow diversion"),
            ],
        )
    if include_unidentified:
        _insert_work(
            db_path,
            work_id="w_local_only_thrombectomy",
            title="Local-only thrombectomy workflow registry",
            abstract="Local corpus record describing thrombectomy workflow without public identifiers.",
            pub_year=2023,
            study_design="registry",
            evidence_tier="moderate",
            citation_count=40,
            subdomain="stroke_thrombectomy",
            identifiers={},
            subjects=[("keyword", "thrombectomy")],
        )
    return db_path


def _m1_case():
    case = parse_case_input(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion"
    )
    return case, select_procedure_family(case)


def _all_text(term) -> set[str]:
    return {term.canonical.casefold(), *(alias.casefold() for alias in term.aliases)}


def _combined_text(terms) -> set[str]:
    return {text for term in terms for text in _all_text(term)}


def _assert_terms_are_structured(terms) -> None:
    assert terms
    assert all(term.provenance for term in terms)
    assert {term.concept_type for term in terms} <= _ALLOWED_CONCEPT_TYPES


def test_corpus_prior_returns_thrombectomy_subdomain_terms(tmp_path):
    db_path = _fixture_db(tmp_path)
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert isinstance(enrichment, PriorEnrichment)
    assert "stroke_thrombectomy" in set(enrichment.subdomain_hints)
    _assert_terms_are_structured(enrichment.expansion_terms)
    assert len(enrichment.expansion_terms) <= 24
    assert any(
        {"mechanical thrombectomy", "endovascular thrombectomy", "large vessel occlusion", "m1 occlusion", "mca occlusion"}
        & _all_text(term)
        and {provenance.source for provenance in term.provenance} == {"local_corpus"}
        and all(provenance.field_path and provenance.matched_value for provenance in term.provenance)
        for term in enrichment.expansion_terms
    )


def test_corpus_prior_maps_m1_segment_occlusion_to_thrombectomy_subdomain(tmp_path):
    db_path = _fixture_db(tmp_path)
    case = parse_case_input("right M1 segment occlusion")
    family = select_procedure_family(case)

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert "stroke_thrombectomy" in set(enrichment.subdomain_hints)


def test_corpus_prior_does_not_map_nonvascular_nonocclusion_m1_to_thrombectomy(tmp_path):
    db_path = _fixture_db(tmp_path)
    case = parse_case_input("left M1 motor cortex glioma resection")
    family = select_procedure_family(case)

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "supratentorial_tumor")

    assert "stroke_thrombectomy" not in set(enrichment.subdomain_hints)


def test_corpus_prior_does_not_map_aneurysm_only_m1_to_thrombectomy(tmp_path):
    db_path = _fixture_db(tmp_path, include_aneurysm=True)
    case = parse_case_input("ruptured M1 aneurysm coiling")
    family = select_procedure_family(case)

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert "stroke_thrombectomy" not in set(enrichment.subdomain_hints)
    assert "aneurysm_sah" in set(enrichment.subdomain_hints)


def test_corpus_prior_returns_seed_sources(tmp_path):
    db_path = _fixture_db(tmp_path)
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    seeds_by_work_id = {seed.work_id: seed for seed in enrichment.seed_sources}
    seed = seeds_by_work_id["w_mr_clean_like"]
    assert seed.pmid == "25517348"
    assert seed.doi == "10.1056/NEJMoa1411587"
    assert seed.pmcid is None
    assert seed.tier == "high"
    assert seed.title_hint == "Randomized trial of mechanical thrombectomy for anterior-circulation stroke"
    assert {provenance.source for provenance in seed.provenance} == {"local_corpus"}
    assert any(provenance.field_path == "works.id" and provenance.matched_value == "w_mr_clean_like" for provenance in seed.provenance)
    assert any(provenance.field_path == "identifiers.pmid" and provenance.matched_value == "25517348" for provenance in seed.provenance)
    assert "w_thrombectomy_outcomes" not in seeds_by_work_id


def test_corpus_prior_seed_sources_respect_limit_and_deterministic_evidence_order(tmp_path):
    db_path = _fixture_db(tmp_path)
    _insert_work(
        db_path,
        work_id="w_guideline",
        title="Guideline thrombectomy selection standards",
        abstract="Guideline recommendations for mechanical thrombectomy in large vessel occlusion.",
        pub_year=2022,
        study_design="guideline",
        evidence_tier="guideline",
        citation_count=50,
        subdomain="stroke_thrombectomy",
        identifiers={"pmid": "55555555"},
        subjects=[("keyword", "mechanical thrombectomy")],
    )
    _insert_work(
        db_path,
        work_id="w_meta_analysis",
        title="Meta-analysis of thrombectomy randomized trials",
        abstract="Meta-analysis of endovascular thrombectomy trials for large vessel occlusion.",
        pub_year=2021,
        study_design="systematic review",
        evidence_tier="meta_analysis",
        citation_count=80,
        subdomain="stroke_thrombectomy",
        identifiers={"doi": "10.1000/meta.thrombectomy"},
        subjects=[("keyword", "endovascular thrombectomy")],
    )
    _insert_work(
        db_path,
        work_id="w_high_citation_only",
        title="Very cited thrombectomy registry",
        abstract="Large registry of thrombectomy outcomes.",
        pub_year=2024,
        study_design="registry",
        evidence_tier="low",
        citation_count=1800,
        subdomain="stroke_thrombectomy",
        identifiers={"pmcid": "PMC9999999"},
        subjects=[("keyword", "thrombectomy")],
    )
    case, family = _m1_case()

    first = NeurosurgeryCorpusPrior(db_path, seed_limit=3).enrich(case, family, "vascular")
    second = NeurosurgeryCorpusPrior(db_path, seed_limit=3).enrich(case, family, "vascular")

    assert [seed.work_id for seed in first.seed_sources] == [
        "w_guideline",
        "w_meta_analysis",
        "w_mr_clean_like",
    ]
    assert [seed.to_dict() for seed in first.seed_sources] == [seed.to_dict() for seed in second.seed_sources]


def test_corpus_prior_seed_order_applies_before_candidate_row_citation_cap(tmp_path):
    db_path = _fixture_db(tmp_path)
    for index in range(260):
        _insert_work(
            db_path,
            work_id=f"w_low_tier_high_citation_{index:03d}",
            title=f"High citation lower-tier thrombectomy registry {index:03d}",
            abstract="Registry data for mechanical thrombectomy in large vessel occlusion.",
            pub_year=2020,
            study_design="registry",
            evidence_tier="low",
            citation_count=5000 - index,
            subdomain="stroke_thrombectomy",
            identifiers={"pmid": f"77777{index:03d}"},
            subjects=[("keyword", "mechanical thrombectomy")],
        )
    _insert_work(
        db_path,
        work_id="w_low_citation_guideline_outside_candidate_cap",
        title="Low citation guideline on thrombectomy selection",
        abstract="Guideline recommendations for endovascular thrombectomy in large vessel occlusion.",
        pub_year=2024,
        study_design="guideline",
        evidence_tier="guideline",
        citation_count=1,
        subdomain="stroke_thrombectomy",
        identifiers={"pmid": "88888888"},
        subjects=[("keyword", "endovascular thrombectomy")],
    )
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path, seed_limit=1).enrich(case, family, "vascular")

    assert [seed.work_id for seed in enrichment.seed_sources] == [
        "w_low_citation_guideline_outside_candidate_cap"
    ]


def test_enrich_case_query_hybrid_merges_curated_and_corpus_seed_sources(tmp_path):
    db_path = _fixture_db(tmp_path)
    case, family = _m1_case()

    plan = enrich_case_query(
        case,
        family,
        profile="vascular",
        retrieval_strategy="hybrid",
        prior_adapter=NeurosurgeryCorpusPrior(db_path),
    )
    mr_clean = [seed for seed in plan["seed_sources"] if seed["pmid"] == "25517348"]

    assert len(mr_clean) == 1
    assert mr_clean[0]["id"] == "mr_clean"
    assert mr_clean[0]["work_id"] == "w_mr_clean_like"
    assert {provenance["source"] for provenance in mr_clean[0]["provenance"]} == {
        "caseprep.evidence_packs.thrombectomy",
        "local_corpus",
    }


def test_corpus_prior_quarantines_off_target_high_citation_terms(tmp_path):
    db_path = _fixture_db(tmp_path, include_aneurysm=True)
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    expanded = _combined_text(enrichment.expansion_terms)
    quarantined = _combined_text(enrichment.quarantined_terms)
    assert {"intracranial aneurysm", "mca aneurysm", "flow diverter", "flow diversion"} & quarantined
    assert not ({"intracranial aneurysm", "mca aneurysm", "flow diverter", "flow diversion"} & expanded)
    if enrichment.quarantined_terms:
        _assert_terms_are_structured(enrichment.quarantined_terms)
        assert any("off-target subdomain" in provenance.notes for term in enrichment.quarantined_terms for provenance in term.provenance)


def test_corpus_prior_records_prior_target_divergence_metadata(tmp_path):
    db_path = _fixture_db(tmp_path, include_aneurysm=True, include_unidentified=True)
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    divergence = enrichment.metadata["prior_target_divergence"]
    assert divergence["prior_sources"] == ["local_corpus"]
    assert "local_corpus" in divergence["target_sources"]
    assert divergence["quarantined_count"] == len(enrichment.quarantined_terms)
    assert divergence["local_corpus_only_records"] == 1
    assert any("quarantined" in warning.casefold() for warning in divergence["warnings"])
    assert any("self-bias" in warning.casefold() for warning in divergence["warnings"])


def test_corpus_prior_respects_term_limit_with_deterministic_order(tmp_path):
    db_path = _fixture_db(tmp_path)
    case, family = _m1_case()

    first = NeurosurgeryCorpusPrior(db_path, term_limit=3).enrich(case, family, "vascular")
    second = NeurosurgeryCorpusPrior(db_path, term_limit=3).enrich(case, family, "vascular")

    assert len(first.expansion_terms) == 3
    assert [term.canonical for term in first.expansion_terms] == [term.canonical for term in second.expansion_terms]
    assert [term.canonical for term in first.expansion_terms] == [
        "mechanical thrombectomy",
        "endovascular thrombectomy",
        "large vessel occlusion",
    ]


def test_corpus_prior_caps_provenance_per_term_deterministically(tmp_path):
    db_path = _fixture_db(tmp_path)
    for index in range(12):
        _insert_work(
            db_path,
            work_id=f"w_extra_thrombectomy_{index}",
            title=f"Additional mechanical thrombectomy cohort {index:02d}",
            abstract="Mechanical thrombectomy for large vessel occlusion.",
            pub_year=2021,
            study_design="cohort study",
            evidence_tier="moderate",
            citation_count=100 + index,
            subdomain="stroke_thrombectomy",
            identifiers={"pmid": f"444444{index:02d}"},
            subjects=[("keyword", "mechanical thrombectomy")],
        )
    case, family = _m1_case()

    first = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")
    second = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")
    first_term = next(term for term in first.expansion_terms if term.canonical == "mechanical thrombectomy")
    second_term = next(term for term in second.expansion_terms if term.canonical == "mechanical thrombectomy")

    assert len(first_term.provenance) <= 8
    assert [item.to_dict() for item in first_term.provenance] == [
        item.to_dict() for item in second_term.provenance
    ]


def test_corpus_prior_empty_subdomain_assignments_yields_no_hints(tmp_path):
    db_path = tmp_path / "empty_assignments.sqlite"
    _create_schema(db_path)
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert enrichment.subdomain_hints == ()
    assert enrichment.expansion_terms == ()
    assert enrichment.quarantined_terms == ()


def test_corpus_prior_missing_db_returns_warning_not_exception(tmp_path):
    missing_path = tmp_path / "does-not-exist.sqlite"
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(missing_path).enrich(case, family, "vascular")

    assert enrichment.expansion_terms == ()
    assert enrichment.seed_sources == ()
    assert enrichment.subdomain_hints == ()
    assert enrichment.quarantined_terms == ()
    assert any(
        ("missing" in warning.casefold() or "unavailable" in warning.casefold())
        and str(missing_path) in warning
        for warning in enrichment.warnings
    )


def test_corpus_prior_constructor_uses_env_db_when_path_omitted(tmp_path, monkeypatch):
    db_path = _fixture_db(tmp_path)
    case, family = _m1_case()
    monkeypatch.setenv("CASEPREP_CORPUS_DB", str(db_path))

    enrichment = NeurosurgeryCorpusPrior().enrich(case, family, "vascular")

    assert isinstance(enrichment, PriorEnrichment)
    assert not any(str(db_path) in warning and "missing" in warning.casefold() for warning in enrichment.warnings)


def test_corpus_prior_opens_sqlite_uri_in_read_only_mode(tmp_path, monkeypatch):
    db_path = _fixture_db(tmp_path)
    case, family = _m1_case()
    original_connect = sqlite3.connect
    calls: list[tuple[str, bool]] = []

    def recording_connect(database, *args, **kwargs):
        calls.append((str(database), bool(kwargs.get("uri"))))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert calls
    assert calls[-1] == (f"file:{db_path}?mode=ro", True)


def test_corpus_prior_schema_mismatch_returns_warning_not_exception(tmp_path):
    db_path = tmp_path / "wrong_schema.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")
    case, family = _m1_case()

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert enrichment.expansion_terms == ()
    assert enrichment.seed_sources == ()
    assert enrichment.subdomain_hints == ()
    assert enrichment.quarantined_terms == ()
    assert any("schema" in warning.casefold() and str(db_path) in warning for warning in enrichment.warnings)


def test_corpus_prior_aneurysm_subdomain_hint(tmp_path):
    db_path = _fixture_db(tmp_path, include_aneurysm=True)
    case = parse_case_input("ruptured MCA aneurysm coiling")
    family = select_procedure_family(case)

    enrichment = NeurosurgeryCorpusPrior(db_path).enrich(case, family, "vascular")

    assert "aneurysm_sah" in set(enrichment.subdomain_hints)
