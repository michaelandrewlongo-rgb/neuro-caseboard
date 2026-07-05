from neuro_caseboard.cv_corpus_build import (
    parse_jats_sections, split_plaintext_sections, _normalize_section,
)


def test_normalize_section_maps_aliases():
    assert _normalize_section("Intro") == "introduction"
    assert _normalize_section("materials and methods") == "methods"
    assert _normalize_section("Conclusions") == "conclusion"
    assert _normalize_section("something-unrecognized") == "other"


def test_parse_jats_sections_extracts_abstract_and_body_secs():
    xml_text = """<article>
      <front><article-meta><abstract><p>Study abstract text here.</p></abstract>
      </article-meta></front>
      <body>
        <sec sec-type="intro"><title>Introduction</title><p>Background text goes here.</p></sec>
        <sec sec-type="methods"><title>Methods</title><p>We did a retrospective review.</p></sec>
        <sec sec-type="coi-statement"><title>Conflicts</title><p>None declared.</p></sec>
      </body>
    </article>"""
    out = parse_jats_sections(xml_text)
    types = [t for t, _ in out]
    assert types == ["abstract", "introduction", "methods"]
    assert "abstract text" in dict(out)["abstract"]


def test_parse_jats_sections_returns_empty_on_malformed_xml():
    assert parse_jats_sections("<not><valid xml") == []


def test_split_plaintext_sections_splits_on_imrad_headers():
    text = (
        "Some running head\n\n"
        "Introduction\n"
        "This study looks at outcomes after treatment.\n\n"
        "Methods\n"
        "Patients were reviewed retrospectively over five years.\n\n"
        "Results\n"
        "Outcomes improved significantly across all subgroups studied.\n"
    )
    out = split_plaintext_sections(text)
    types = [t for t, _ in out]
    assert "introduction" in types and "methods" in types and "results" in types


def test_split_plaintext_sections_falls_back_to_other_when_no_headers():
    text = "just a wall of text with no recognizable section headers at all here " * 3
    out = split_plaintext_sections(text)
    assert len(out) == 1 and out[0][0] == "other"


def test_split_plaintext_sections_drops_short_fragments():
    assert split_plaintext_sections("too short") == []


import sqlite3

from neuro_caseboard.cv_corpus_build import create_schema, existing_pmids, insert_work


def test_insert_work_round_trips_through_schema():
    con = sqlite3.connect(":memory:")
    create_schema(con)
    assert existing_pmids(con) == set()

    insert_work(con, "12345", "A Study of Things", "Stroke", 2020, "10.1/xyz",
               [("abstract", "Background and results of the study go here in full.")])
    con.commit()

    assert existing_pmids(con) == {"12345"}
    work = con.execute("SELECT title, journal_title, pub_year FROM works WHERE id=?",
                       ("12345",)).fetchone()
    assert work == ("A Study of Things", "Stroke", 2020)
    ids = con.execute("SELECT scheme, value FROM identifiers WHERE work_id=? ORDER BY scheme",
                      ("12345",)).fetchall()
    assert ids == [("doi", "10.1/xyz"), ("pmid", "12345")]
    passages = con.execute("SELECT section_type, content FROM text_passages WHERE work_id=?",
                           ("12345",)).fetchall()
    assert passages == [("abstract", "Background and results of the study go here in full.")]


def test_insert_work_without_doi_omits_doi_identifier():
    con = sqlite3.connect(":memory:")
    create_schema(con)
    insert_work(con, "999", "T", "J", 2021, None, [("other", "x" * 50)])
    con.commit()
    schemes = {s for (s,) in con.execute(
        "SELECT scheme FROM identifiers WHERE work_id=?", ("999",))}
    assert schemes == {"pmid"}


def test_insert_work_is_idempotent_via_or_replace():
    con = sqlite3.connect(":memory:")
    create_schema(con)
    insert_work(con, "1", "First title", "J", 2019, None, [("other", "x" * 50)])
    insert_work(con, "1", "Updated title", "J", 2019, None, [("other", "y" * 50)])
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1
    title = con.execute("SELECT title FROM works WHERE id=?", ("1",)).fetchone()[0]
    assert title == "Updated title"
    passages = con.execute("SELECT content FROM text_passages WHERE work_id=?",
                           ("1",)).fetchall()
    assert passages == [("y" * 50,)]
