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


from neuro_caseboard.cv_corpus_build import copy_from_big_db


def _make_big_db_fixture(path):
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE works (id TEXT PRIMARY KEY, title TEXT, journal_title TEXT,
                            pub_year INTEGER, study_design TEXT, abstract TEXT);
        CREATE TABLE identifiers (id TEXT PRIMARY KEY, work_id TEXT, scheme TEXT, value TEXT);
        CREATE TABLE text_passages (id TEXT, work_id TEXT, section_type TEXT,
                                    content TEXT, sequence_number INTEGER);
    """)
    con.execute("INSERT INTO works VALUES ('w1', 'Big DB Title', 'Neurosurgery', 2018, "
               "'rct', 'Abstract text.')")
    con.execute("INSERT INTO identifiers VALUES ('i1', 'w1', 'pmid', '23387822')")
    con.execute("INSERT INTO identifiers VALUES ('i2', 'w1', 'doi', '10.1/abc')")
    con.execute("INSERT INTO text_passages VALUES ('p1', 'w1', 'introduction', "
               "'Intro text here.', 0)")
    con.execute("INSERT INTO text_passages VALUES ('p2', 'w1', 'results', "
               "'Results text here.', 1)")
    con.commit()
    con.close()


def test_copy_from_big_db_returns_work_and_ordered_passages(tmp_path):
    db_path = tmp_path / "cerebrovascular_fulltext.sqlite"
    _make_big_db_fixture(db_path)
    out = copy_from_big_db(str(db_path), "23387822")
    assert out["title"] == "Big DB Title"
    assert out["journal"] == "Neurosurgery"
    assert out["year"] == 2018
    assert out["doi"] == "10.1/abc"
    assert out["passages"] == [("introduction", "Intro text here."),
                               ("results", "Results text here.")]


def test_copy_from_big_db_returns_none_for_missing_pmid(tmp_path):
    db_path = tmp_path / "cerebrovascular_fulltext.sqlite"
    _make_big_db_fixture(db_path)
    assert copy_from_big_db(str(db_path), "00000000") is None


def test_copy_from_big_db_returns_none_when_db_missing(tmp_path):
    assert copy_from_big_db(str(tmp_path / "nope.sqlite"), "23387822") is None


from neuro_caseboard.cv_corpus_build import load_have_list, chapter_dir_map


def test_load_have_list_parses_csv_rows(tmp_path):
    csv_path = tmp_path / "have-list.csv"
    csv_path.write_text(
        "pmid,chapter,format,file,access,year,journal,doi,title,authors\n"
        "111,3,pdf,papers/x.pdf,Open access,2020,Stroke,10.1/a,A Title,Smith J\n"
    )
    rows = load_have_list(str(csv_path))
    assert rows == [{
        "pmid": "111", "chapter": "3", "format": "pdf", "file": "papers/x.pdf",
        "access": "Open access", "year": "2020", "journal": "Stroke",
        "doi": "10.1/a", "title": "A Title", "authors": "Smith J",
    }]


def test_chapter_dir_map_resolves_by_leading_chapter_number(tmp_path):
    root = tmp_path / "cv_full_text"
    (root / "Ch03_Noninvasive-imaging").mkdir(parents=True)
    (root / "Ch47_Spinal-angiography-anatomy").mkdir(parents=True)
    (root / "not_a_chapter_dir").mkdir(parents=True)
    mapping = chapter_dir_map(str(root))
    assert mapping[3].name == "Ch03_Noninvasive-imaging"
    assert mapping[47].name == "Ch47_Spinal-angiography-anatomy"
    assert set(mapping) == {3, 47}
