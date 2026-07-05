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
