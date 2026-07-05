# Cerebrovascular Curated Full-Text Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user flag an Ask question as cerebrovascular and have it search a new 508-article hand-curated full-text corpus, cited `[D#]` via the existing Lane C machinery.

**Architecture:** Build a standalone SQLite DB (`cv_curated_fulltext.sqlite`, schema-identical to Lane C's `works`/`identifiers`/`text_passages`) from `cv_full_text/` + `have-list.csv`, reusing already-extracted rows from the sibling `cv-curric` project's big automated corpus where a PMID overlaps (354/508), and freshly parsing the rest (~154) from JATS XML or plaintext. Wire a `cerebrovascular` boolean through `AskRequest` → `qa.answer_question`/`qa_stream.stream_answer` → an overridden `CorpusConfig` scoped to just this new DB, and a checkbox in the web Ask UI.

**Tech Stack:** Python (stdlib `sqlite3`, `csv`, `xml.etree.ElementTree`, `re`), pytest, FastAPI (`api/server.py`), React/TypeScript (`web/src`).

## Global Constraints

- Reuse Lane C's existing schema, retrieval code (`neuro_caseboard/corpus.py`), and `[D#]` citation rendering exactly — no new bracket style, no synthesis prompt changes.
- Never modify or write into `/mnt/c/dev/NSGY_DB_lean/` — that belongs to the sibling `cv-curric` project and is read-only for this feature.
- The new corpus lives at `~/neuro-caseboard-corpus/fulltext/cv_curated_fulltext.sqlite`; its FTS5 sidecar reuses the existing `~/.cache/neuro_caseboard/corpus_fts/` cache dir as `cv_curated_fts.sqlite` (same convention `build_corpus_fts.py` already uses for the other seven DBs).
- Ingestion is idempotent/re-runnable: re-running after adding more curated papers only processes PMIDs not already in the output DB.
- Failure-safe: any error in the new lane yields `[]` and never blocks Lanes A/B, matching `retrieve_corpus_for_weave`'s existing contract.
- No test touches the real 7.3GB external DB or writes the real curated DB — all DB-shaped tests use tiny fixture SQLite files built inline in the test.

---

## Task 1: Section-tagging parsers (JATS XML + plaintext fallback)

**Files:**
- Create: `neuro_caseboard/cv_corpus_build.py`
- Test: `tests/test_cv_corpus_build.py`

**Interfaces:**
- Produces: `parse_jats_sections(xml_text: str) -> list[tuple[str, str]]`, `split_plaintext_sections(text: str) -> list[tuple[str, str]]`, `_normalize_section(label: str) -> str` — each tuple is `(section_type, content)`; `section_type` is always one of `title/abstract/introduction/methods/results/discussion/conclusion/case_report/other` (Lane C's fixed vocabulary in `neuro_caseboard/corpus.py:29-31`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cv_corpus_build.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cv_corpus_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_caseboard.cv_corpus_build'`

- [ ] **Step 3: Write the implementation**

```python
# neuro_caseboard/cv_corpus_build.py
"""Ingestion for the cerebrovascular curated full-text corpus (Lane C extension).

Builds a standalone SQLite DB (schema-identical to neuro_caseboard/corpus.py's
works/identifiers/text_passages) from cv_full_text/ + have-list.csv, reusing
already-extracted rows from the sibling cv-curric big corpus where a PMID
overlaps, and freshly parsing the rest from JATS XML or plaintext.
"""
from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

_MIN_PASSAGE_CHARS = 40

_SECTION_ALIASES = {
    "abstract": "abstract",
    "background": "introduction",
    "intro": "introduction",
    "introduction": "introduction",
    "materials and methods": "methods",
    "material and methods": "methods",
    "materials|methods": "methods",
    "methods": "methods",
    "methodology": "methods",
    "results": "results",
    "discussion": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "case report": "case_report",
    "case presentation": "case_report",
    "case": "case_report",
}

_SKIP_SEC_TYPES = {
    "coi-statement", "conflict-of-interest", "disclaimer", "funding-information",
    "funding", "data-availability", "supplementary-material", "author-contributions",
    "ethics-statement",
}

_HEADER_RE = re.compile(
    r"^[ \t]*(abstract|background|introduction|materials and methods|"
    r"material and methods|methods|methodology|results|discussion|"
    r"conclusions?|case report|case presentation)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _normalize_section(label: str) -> str:
    return _SECTION_ALIASES.get((label or "").strip().lower(), "other")


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def parse_jats_sections(xml_text: str) -> list:
    """Top-level abstract + body <sec> elements from a JATS/NLM full-text XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    passages = []
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        text = _clean("".join(abstract_el.itertext()))
        if len(text) >= _MIN_PASSAGE_CHARS:
            passages.append(("abstract", text))
    body = root.find(".//body")
    if body is None:
        return passages
    for sec in body.findall("sec"):
        sec_type_attr = (sec.get("sec-type") or "").strip().lower()
        if sec_type_attr in _SKIP_SEC_TYPES:
            continue
        label = sec_type_attr
        if not label:
            title_el = sec.find("title")
            label = title_el.text if title_el is not None and title_el.text else ""
        text = _clean("".join(sec.itertext()))
        if len(text) >= _MIN_PASSAGE_CHARS:
            passages.append((_normalize_section(label), text))
    return passages


def split_plaintext_sections(text: str) -> list:
    """Regex IMRAD-header splitter for a plaintext-only article (no XML available)."""
    text = text or ""
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        body = _clean(text)
        return [("other", body)] if len(body) >= _MIN_PASSAGE_CHARS else []
    passages = []
    lead = _clean(text[: matches[0].start()])
    if len(lead) >= _MIN_PASSAGE_CHARS:
        passages.append(("other", lead))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = _clean(text[start:end])
        if len(chunk) >= _MIN_PASSAGE_CHARS:
            passages.append((_normalize_section(m.group(1)), chunk))
    return passages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cv_corpus_build.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cv_corpus_build.py tests/test_cv_corpus_build.py
git commit -m "feat(cv-corpus): add JATS/plaintext section-tagging parsers"
```

---

## Task 2: SQLite schema + write helpers

**Files:**
- Modify: `neuro_caseboard/cv_corpus_build.py`
- Modify: `tests/test_cv_corpus_build.py`

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: `create_schema(con: sqlite3.Connection) -> None`, `existing_pmids(con) -> set[str]`, `insert_work(con, pmid, title, journal, year, doi, passages, *, study_design=None, abstract=None, primary_domain="cerebrovascular") -> None` where `passages` is `list[tuple[str, str]]` as produced by Task 1's parsers.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_cv_corpus_build.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cv_corpus_build.py -k insert_work -v`
Expected: FAIL with `ImportError: cannot import name 'create_schema'`

- [ ] **Step 3: Write the implementation**

```python
# append to neuro_caseboard/cv_corpus_build.py

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY, title TEXT, normalized_title TEXT, pub_year INTEGER,
    journal_title TEXT, primary_domain TEXT, study_design TEXT, evidence_tier TEXT,
    abstract TEXT
);
CREATE TABLE IF NOT EXISTS identifiers (
    id TEXT PRIMARY KEY, work_id TEXT, scheme TEXT, value TEXT
);
CREATE TABLE IF NOT EXISTS text_passages (
    id TEXT, work_id TEXT, section_type TEXT, content TEXT, sequence_number INTEGER
);
CREATE INDEX IF NOT EXISTS idx_identifiers_scheme_value ON identifiers(scheme, value);
CREATE INDEX IF NOT EXISTS idx_text_passages_work_id ON text_passages(work_id);
"""


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA_SQL)


def existing_pmids(con: sqlite3.Connection) -> set:
    return {row[0] for row in con.execute(
        "SELECT value FROM identifiers WHERE scheme='pmid'")}


def insert_work(con, pmid, title, journal, year, doi, passages, *, study_design=None,
                abstract=None, primary_domain="cerebrovascular") -> None:
    con.execute(
        "INSERT OR REPLACE INTO works (id, title, normalized_title, pub_year, "
        "journal_title, primary_domain, study_design, evidence_tier, abstract) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pmid, title or "", (title or "").strip().lower(), year, journal or "",
         primary_domain, study_design, None, abstract))
    con.execute("DELETE FROM identifiers WHERE work_id=?", (pmid,))
    con.execute("INSERT INTO identifiers (id, work_id, scheme, value) VALUES (?,?,?,?)",
               (f"{pmid}-pmid", pmid, "pmid", pmid))
    if doi:
        con.execute("INSERT INTO identifiers (id, work_id, scheme, value) VALUES (?,?,?,?)",
                   (f"{pmid}-doi", pmid, "doi", doi))
    con.execute("DELETE FROM text_passages WHERE work_id=?", (pmid,))
    for seq, (section_type, content) in enumerate(passages):
        con.execute(
            "INSERT INTO text_passages (id, work_id, section_type, content, "
            "sequence_number) VALUES (?,?,?,?,?)",
            (f"{pmid}-{seq}", pmid, section_type, content, seq))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cv_corpus_build.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cv_corpus_build.py tests/test_cv_corpus_build.py
git commit -m "feat(cv-corpus): add SQLite schema + idempotent work-insert helpers"
```

---

## Task 3: Copy-from-big-DB helper

**Files:**
- Modify: `neuro_caseboard/cv_corpus_build.py`
- Modify: `tests/test_cv_corpus_build.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `copy_from_big_db(big_db_path: str, pmid: str) -> dict | None` — `None` if the DB file doesn't exist or the PMID isn't in it; otherwise `{"title", "journal", "year", "study_design", "abstract", "doi", "passages"}` where `passages` is `list[tuple[str, str]]` ordered by `sequence_number`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_cv_corpus_build.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cv_corpus_build.py -k copy_from_big_db -v`
Expected: FAIL with `ImportError: cannot import name 'copy_from_big_db'`

- [ ] **Step 3: Write the implementation**

```python
# append to neuro_caseboard/cv_corpus_build.py
import os


def copy_from_big_db(big_db_path: str, pmid: str):
    """Look up `pmid` in an already-built Lane C source DB (e.g. the sibling
    cv-curric project's cerebrovascular_fulltext.sqlite) and return its work +
    passages, or None if the DB or PMID isn't present. Read-only; never writes."""
    if not os.path.exists(big_db_path):
        return None
    con = sqlite3.connect(f"file:{big_db_path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT work_id FROM identifiers WHERE scheme='pmid' AND value=?",
            (pmid,)).fetchone()
        if row is None:
            return None
        work_id = row[0]
        w = con.execute(
            "SELECT title, journal_title, pub_year, study_design, abstract "
            "FROM works WHERE id=?", (work_id,)).fetchone()
        if w is None:
            return None
        title, journal, year, study_design, abstract = w
        doi_row = con.execute(
            "SELECT value FROM identifiers WHERE scheme='doi' AND work_id=?",
            (work_id,)).fetchone()
        passages = con.execute(
            "SELECT section_type, content FROM text_passages WHERE work_id=? "
            "ORDER BY sequence_number", (work_id,)).fetchall()
        return {
            "title": title, "journal": journal, "year": year,
            "study_design": study_design, "abstract": abstract,
            "doi": doi_row[0] if doi_row else None,
            "passages": [(s, c) for s, c in passages],
        }
    finally:
        con.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cv_corpus_build.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cv_corpus_build.py tests/test_cv_corpus_build.py
git commit -m "feat(cv-corpus): reuse already-extracted rows from the big Lane C DB by PMID"
```

---

## Task 4: have-list.csv loader + chapter-directory resolver

**Files:**
- Modify: `neuro_caseboard/cv_corpus_build.py`
- Modify: `tests/test_cv_corpus_build.py`

**Interfaces:**
- Produces: `load_have_list(csv_path) -> list[dict]` (one dict per CSV row, `csv.DictReader` field names), `chapter_dir_map(cv_full_text_root) -> dict[int, Path]` (chapter number → its `Ch{NN}_...` directory).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_cv_corpus_build.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cv_corpus_build.py -k "have_list or chapter_dir" -v`
Expected: FAIL with `ImportError: cannot import name 'load_have_list'`

- [ ] **Step 3: Write the implementation**

```python
# append to neuro_caseboard/cv_corpus_build.py
import csv

_CHAPTER_DIR_RE = re.compile(r"^Ch(\d+)_")


def load_have_list(csv_path: str) -> list:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chapter_dir_map(cv_full_text_root: str) -> dict:
    root = Path(cv_full_text_root)
    out = {}
    for d in root.iterdir():
        if not d.is_dir():
            continue
        m = _CHAPTER_DIR_RE.match(d.name)
        if m:
            out[int(m.group(1))] = d
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cv_corpus_build.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cv_corpus_build.py tests/test_cv_corpus_build.py
git commit -m "feat(cv-corpus): add have-list.csv loader + chapter directory resolver"
```

---

## Task 5: Orchestration (`build()`) + CLI entry point

**Files:**
- Modify: `neuro_caseboard/cv_corpus_build.py`
- Modify: `tests/test_cv_corpus_build.py`
- Create: `scripts/build_cv_curated_corpus.py`

**Interfaces:**
- Consumes: every helper produced in Tasks 1-4.
- Produces: `build(csv_path, cv_full_text_root, big_db_path, out_db_path, log=print) -> dict` returning `{"copied": int, "extracted": int, "skipped": int}`; `main(argv=None) -> None` (CLI wrapper around `build`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_cv_corpus_build.py
from neuro_caseboard.cv_corpus_build import build


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_copies_overlap_and_extracts_new_and_skips_missing(tmp_path):
    # Big DB has PMID 111 (the "already extracted" case).
    big_db = tmp_path / "cerebrovascular_fulltext.sqlite"
    _make_big_db_fixture(big_db)  # defines pmid 23387822 from Task 3's fixture

    root = tmp_path / "cv_full_text"
    ch3 = root / "Ch03_Noninvasive-imaging"
    # PMID with real XML → parsed via parse_jats_sections.
    _write(ch3 / "222.xml", (
        "<article><body><sec sec-type=\"results\"><title>Results</title>"
        "<p>Fresh XML results text of sufficient length to keep as a passage.</p>"
        "</sec></body></article>"))
    # PMID with only .txt → parsed via split_plaintext_sections.
    _write(ch3 / "333.txt", (
        "Introduction\nThis plaintext-only article has an introduction section here.\n"))
    # PMID with neither file present → must be skipped, not error the whole run.
    csv_path = tmp_path / "have-list.csv"
    csv_path.write_text(
        "pmid,chapter,format,file,access,year,journal,doi,title,authors\n"
        "23387822,3,xml,x,PMC free,2013,Neurosurgery,,Overlap Title,\n"
        "222,3,xml,x,Open access,2022,Stroke,10.1/xyz,Fresh XML Title,\n"
        "333,3,txt,x,Open access,2021,JNS,,Plaintext Title,\n"
        "444,3,pdf,x,NEEDS LIBRARY,2019,JNS,,Missing File Title,\n"
    )
    out_db = tmp_path / "out" / "cv_curated_fulltext.sqlite"

    result = build(str(csv_path), str(root), str(big_db), str(out_db))
    assert result == {"copied": 1, "extracted": 2, "skipped": 1}

    con = sqlite3.connect(str(out_db))
    assert existing_pmids(con) == {"23387822", "222", "333"}
    overlap_title = con.execute(
        "SELECT title FROM works WHERE id='23387822'").fetchone()[0]
    assert overlap_title == "Big DB Title"  # came from the big DB, not the CSV


def test_build_is_idempotent_on_rerun(tmp_path):
    big_db = tmp_path / "cerebrovascular_fulltext.sqlite"
    _make_big_db_fixture(big_db)
    root = tmp_path / "cv_full_text"
    _write(root / "Ch03_Noninvasive-imaging" / "222.txt",
          "Introduction\nSome fresh plaintext article introduction content lives here.\n")
    csv_path = tmp_path / "have-list.csv"
    csv_path.write_text(
        "pmid,chapter,format,file,access,year,journal,doi,title,authors\n"
        "222,3,txt,x,Open access,2022,Stroke,,Title,\n")
    out_db = tmp_path / "cv_curated_fulltext.sqlite"

    first = build(str(csv_path), str(root), str(big_db), str(out_db))
    second = build(str(csv_path), str(root), str(big_db), str(out_db))
    assert first == {"copied": 0, "extracted": 1, "skipped": 0}
    assert second == {"copied": 0, "extracted": 0, "skipped": 0}  # nothing left to do
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cv_corpus_build.py -k test_build -v`
Expected: FAIL with `ImportError: cannot import name 'build'`

- [ ] **Step 3: Write the implementation**

```python
# append to neuro_caseboard/cv_corpus_build.py

def build(csv_path, cv_full_text_root, big_db_path, out_db_path, log=print) -> dict:
    chapters = chapter_dir_map(cv_full_text_root)
    rows = load_have_list(csv_path)

    Path(out_db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out_db_path)
    create_schema(con)
    have = existing_pmids(con)

    copied = extracted = skipped = 0
    for row in rows:
        pmid = (row.get("pmid") or "").strip()
        if not pmid or pmid in have:
            continue

        big = copy_from_big_db(big_db_path, pmid)
        if big is not None:
            insert_work(con, pmid, big["title"], big["journal"], big["year"],
                       row.get("doi") or big["doi"], big["passages"],
                       study_design=big["study_design"], abstract=big["abstract"])
            copied += 1
            continue

        chapter_num = int(row["chapter"]) if (row.get("chapter") or "").strip().isdigit() else None
        chapter_dir = chapters.get(chapter_num) if chapter_num is not None else None
        passages = []
        if chapter_dir is not None:
            xml_path = chapter_dir / f"{pmid}.xml"
            txt_path = chapter_dir / f"{pmid}.txt"
            if xml_path.exists():
                passages = parse_jats_sections(
                    xml_path.read_text(encoding="utf-8", errors="ignore"))
            elif txt_path.exists():
                passages = split_plaintext_sections(
                    txt_path.read_text(encoding="utf-8", errors="ignore"))

        if not passages:
            log(f"[skip] {pmid}: no source text found under chapter {chapter_num}")
            skipped += 1
            continue

        title = row.get("title") or ""
        if title:
            passages = [("title", title)] + passages
        year = int(row["year"]) if (row.get("year") or "").strip().isdigit() else None
        insert_work(con, pmid, title, row.get("journal") or "", year,
                   row.get("doi") or None, passages)
        extracted += 1

    con.commit()
    con.close()
    log(f"[done] copied={copied} extracted={extracted} skipped={skipped}")
    return {"copied": copied, "extracted": extracted, "skipped": skipped}


def main(argv=None) -> None:
    import argparse
    import os as _os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="cv_full_text/have-list.csv")
    parser.add_argument("--source-root", default="cv_full_text")
    parser.add_argument("--big-db", default=_os.path.join(
        _os.environ.get("CORPUS_SOURCE_DIR", "/mnt/c/dev/NSGY_DB_lean/fulltext"),
        "cerebrovascular_fulltext.sqlite"))
    parser.add_argument("--out", default=str(
        Path.home() / "neuro-caseboard-corpus" / "fulltext" / "cv_curated_fulltext.sqlite"))
    args = parser.parse_args(argv)
    build(args.csv, args.source_root, args.big_db, args.out)


if __name__ == "__main__":
    main()
```

```python
# scripts/build_cv_curated_corpus.py
#!/usr/bin/env python3
"""CLI wrapper — see neuro_caseboard.cv_corpus_build for the implementation."""
from neuro_caseboard.cv_corpus_build import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cv_corpus_build.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cv_corpus_build.py tests/test_cv_corpus_build.py scripts/build_cv_curated_corpus.py
git commit -m "feat(cv-corpus): add idempotent build() orchestration + CLI entry point"
```

---

## Task 6: Thread `corpus_config` through the public `qa.answer_question()`

**Files:**
- Modify: `neuro_caseboard/qa.py:227-242`
- Modify: `tests/test_qa.py`

**Interfaces:**
- Consumes: `neuro_caseboard.corpus.CorpusConfig` (existing type, unchanged).
- Produces: `answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None, skip_disambiguation=False, corpus_query=None, corpus_config=None) -> QAResult` — the new `corpus_config` param, when given, reaches `_answer_question_woven` (which already accepts it) instead of always defaulting to `load_corpus_config()`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_qa.py
def test_answer_question_forwards_corpus_config(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    import neuro_caseboard.qa as qa
    captured = {}

    def _spy(*a, **k):
        captured.update(k)
        return "WOVEN"

    monkeypatch.setattr(qa, "_answer_question_woven", _spy)
    sentinel = object()
    assert qa.answer_question("q", corpus_config=sentinel) == "WOVEN"
    assert captured.get("corpus_config") is sentinel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_qa.py -k forwards_corpus_config -v`
Expected: FAIL with `TypeError: answer_question() got an unexpected keyword argument 'corpus_config'`

- [ ] **Step 3: Write the implementation**

Modify `neuro_caseboard/qa.py:227-242` from:

```python
def answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None,
                    skip_disambiguation=False, corpus_query=None) -> QAResult:
    """Run Lane A and Lane B concurrently. Lane A errors propagate; Lane B failures drop
    the section. `lane_a`/`lane_b` are injectable no-arg callables (for tests).

    When `LITERATURE_WEAVE` is on and no lanes are injected, delegates to the woven
    orchestrator (_answer_question_woven) which produces one integrated answer."""
    # Woven mode (flag-gated): one integrated answer. Only when no lanes were injected, so
    # the separate-path tests (which inject lane_a/lane_b) are unaffected.
    if lane_a is None and lane_b is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
        if lit_config.weave:
            return _answer_question_woven(question, config=config, force=force,
                                          lit_config=lit_config, corpus_query=corpus_query,
                                          skip_disambiguation=skip_disambiguation)
```

to:

```python
def answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None,
                    skip_disambiguation=False, corpus_query=None,
                    corpus_config=None) -> QAResult:
    """Run Lane A and Lane B concurrently. Lane A errors propagate; Lane B failures drop
    the section. `lane_a`/`lane_b` are injectable no-arg callables (for tests).

    When `LITERATURE_WEAVE` is on and no lanes are injected, delegates to the woven
    orchestrator (_answer_question_woven) which produces one integrated answer.
    `corpus_config`, when given, scopes/enables Lane C for this call only (e.g. the
    per-request cerebrovascular-corpus opt-in) instead of the global env default."""
    # Woven mode (flag-gated): one integrated answer. Only when no lanes were injected, so
    # the separate-path tests (which inject lane_a/lane_b) are unaffected.
    if lane_a is None and lane_b is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
        if lit_config.weave:
            return _answer_question_woven(question, config=config, force=force,
                                          lit_config=lit_config, corpus_query=corpus_query,
                                          corpus_config=corpus_config,
                                          skip_disambiguation=skip_disambiguation)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_qa.py -v`
Expected: PASS (all existing tests + the new one)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/qa.py tests/test_qa.py
git commit -m "feat(cv-corpus): thread corpus_config through answer_question()"
```

---

## Task 7: `AskRequest.cerebrovascular` opt-in wired through both Ask endpoints

**Files:**
- Modify: `api/server.py:293-300` (`AskRequest`)
- Modify: `api/server.py:444-474` (`run_ask_job`, `ask_start`)
- Modify: `api/server.py:498-517` (`ask`)
- Test: `tests/test_api_ask_stream.py`
- Test: `tests/test_api_ask_verification.py` (or a new focused test file if that one doesn't fit — see Step 1)

**Interfaces:**
- Consumes: `neuro_caseboard.corpus.load_corpus_config`, `dataclasses.replace`.
- Produces: `AskRequest.cerebrovascular: bool = False`; a module-level helper `_cerebrovascular_corpus_config() -> CorpusConfig`; `run_ask_job(job, question, skip_disambiguation, corpus_config=None)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_api_ask_stream.py

def test_cerebrovascular_flag_scopes_corpus_config_on_stream_start(monkeypatch):
    import api.server as server
    captured = {}

    def _fake_stream_answer(question, emit, **kwargs):
        captured.update(kwargs)
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start",
                         json={"question": "q", "cerebrovascular": True}).json()["job_id"]
    client.get(f"/api/ask/stream/{job_id}?cursor=0")  # drive the job thread to completion

    cfg = captured.get("corpus_config")
    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.dbs == ["cv_curated"]


def test_cerebrovascular_flag_defaults_off(monkeypatch):
    import api.server as server
    captured = {}

    def _fake_stream_answer(question, emit, **kwargs):
        captured.update(kwargs)
        emit({"type": "done"})

    monkeypatch.setattr("neuro_caseboard.qa_stream.stream_answer", _fake_stream_answer)
    client = TestClient(server.app)
    job_id = client.post("/api/ask/start", json={"question": "q"}).json()["job_id"]
    client.get(f"/api/ask/stream/{job_id}?cursor=0")
    assert captured.get("corpus_config") is None
```

```python
# new file: tests/test_api_ask_cerebrovascular.py
"""POST /api/ask with cerebrovascular=true scopes Lane C to the curated corpus DB."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def test_blocking_ask_forwards_scoped_corpus_config(monkeypatch):
    import api.server as server
    captured = {}

    def _fake_answer_question(question, **kwargs):
        captured.update(kwargs)
        from neuro_caseboard.qa import QAResult
        return QAResult(answer="ok", citations=[], figures=[])

    monkeypatch.setattr("neuro_caseboard.qa.answer_question", _fake_answer_question)
    client = TestClient(server.app)
    resp = client.post("/api/ask", json={"question": "q", "cerebrovascular": True})
    assert resp.status_code == 200
    cfg = captured.get("corpus_config")
    assert cfg is not None and cfg.enabled is True and cfg.dbs == ["cv_curated"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_ask_stream.py tests/test_api_ask_cerebrovascular.py -v`
Expected: FAIL — `cerebrovascular` is not a recognized field / `captured` stays empty (assertion errors)

- [ ] **Step 3: Write the implementation**

Modify `api/server.py:293-300` from:

```python
class AskRequest(BaseModel):
    question: str
    # Local single-user tool: default to bypassing the GPU-readiness guard so it "just runs".
    # A real GpuNotReadyError (e.g. genuinely out of memory) is still surfaced honestly.
    force: bool = True
    # Set by the SPA on a variant-pick re-entry: the question is already a disambiguated
    # variant rewrite (unambiguous by construction), so skip the gate + analyze pass.
    skip_disambiguation: bool = False
```

to:

```python
class AskRequest(BaseModel):
    question: str
    # Local single-user tool: default to bypassing the GPU-readiness guard so it "just runs".
    # A real GpuNotReadyError (e.g. genuinely out of memory) is still surfaced honestly.
    force: bool = True
    # Set by the SPA on a variant-pick re-entry: the question is already a disambiguated
    # variant rewrite (unambiguous by construction), so skip the gate + analyze pass.
    skip_disambiguation: bool = False
    # Per-request opt-in: scopes Lane C ([D#]) to the curated cerebrovascular corpus
    # instead of the global (default-off) CORPUS_RETRIEVAL env setting.
    cerebrovascular: bool = False


def _cerebrovascular_corpus_config():
    """Lane C config scoped to the standalone curated corpus (see
    neuro_caseboard/cv_corpus_build.py), never the sibling cv-curric project's DB."""
    import dataclasses
    import os
    from pathlib import Path
    from neuro_caseboard.corpus import load_corpus_config
    source_dir = os.environ.get(
        "CV_CURATED_SOURCE_DIR", str(Path.home() / "neuro-caseboard-corpus" / "fulltext"))
    return dataclasses.replace(load_corpus_config(), enabled=True,
                               dbs=["cv_curated"], source_dir=source_dir)
```

Modify `api/server.py:444-474` from:

```python
def run_ask_job(job: AskJob, question: str, skip_disambiguation: bool) -> None:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_caseboard import qa_stream
    try:
        qa_stream.stream_answer(question, job.emit, force=True,
                                skip_disambiguation=skip_disambiguation)
    except GpuNotReadyError as e:
        job.emit({"type": "unavailable", "reason": f"GPU not ready: {e}"})
        job.emit({"type": "done"})
    except Exception as e:
        job.emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
        job.emit({"type": "done"})
    finally:
        if not job.done:                       # the orchestrator always ends with done, but be safe
            job.emit({"type": "done"})


@app.post("/api/ask/start")
def ask_start(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"error": "empty question"})
    job_id = uuid.uuid4().hex[:16]
    job = AskJob(job_id)
    _ASK_JOBS[job_id] = job
    _ASK_JOBS.move_to_end(job_id)
    while len(_ASK_JOBS) > _ASK_JOBS_MAX:
        _ASK_JOBS.popitem(last=False)
    threading.Thread(target=run_ask_job, args=(job, question, req.skip_disambiguation),
                     daemon=True).start()
    return {"job_id": job_id}
```

to:

```python
def run_ask_job(job: AskJob, question: str, skip_disambiguation: bool,
                corpus_config=None) -> None:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_caseboard import qa_stream
    try:
        qa_stream.stream_answer(question, job.emit, force=True,
                                skip_disambiguation=skip_disambiguation,
                                corpus_config=corpus_config)
    except GpuNotReadyError as e:
        job.emit({"type": "unavailable", "reason": f"GPU not ready: {e}"})
        job.emit({"type": "done"})
    except Exception as e:
        job.emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
        job.emit({"type": "done"})
    finally:
        if not job.done:                       # the orchestrator always ends with done, but be safe
            job.emit({"type": "done"})


@app.post("/api/ask/start")
def ask_start(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"error": "empty question"})
    job_id = uuid.uuid4().hex[:16]
    job = AskJob(job_id)
    _ASK_JOBS[job_id] = job
    _ASK_JOBS.move_to_end(job_id)
    while len(_ASK_JOBS) > _ASK_JOBS_MAX:
        _ASK_JOBS.popitem(last=False)
    corpus_config = _cerebrovascular_corpus_config() if req.cerebrovascular else None
    threading.Thread(target=run_ask_job,
                     args=(job, question, req.skip_disambiguation, corpus_config),
                     daemon=True).start()
    return {"job_id": job_id}
```

Modify `api/server.py:498-517` (the blocking `/api/ask`) from:

```python
@app.post("/api/ask")
def ask(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty question"})

    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import Clarification
    from neuro_caseboard.qa import answer_question

    try:
        result = answer_question(question, force=req.force,
                                 skip_disambiguation=req.skip_disambiguation)
```

to:

```python
@app.post("/api/ask")
def ask(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"kind": "error", "error": "empty question"})

    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import Clarification
    from neuro_caseboard.qa import answer_question

    corpus_config = _cerebrovascular_corpus_config() if req.cerebrovascular else None
    try:
        result = answer_question(question, force=req.force,
                                 skip_disambiguation=req.skip_disambiguation,
                                 corpus_config=corpus_config)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_ask_stream.py tests/test_api_ask_cerebrovascular.py tests/test_api_ask_verification.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/server.py tests/test_api_ask_stream.py tests/test_api_ask_cerebrovascular.py
git commit -m "feat(cv-corpus): add cerebrovascular opt-in to both Ask endpoints"
```

---

## Task 8: Web — Ask page checkbox

**Files:**
- Modify: `web/src/lib/api.ts:101-138`
- Modify: `web/src/pages/Ask.tsx:34-153`
- Test: `web/src/lib/api.test.ts` (create if no such file exists — check first with `ls web/src/lib/*.test.ts`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `askQuestion(question, signal?, skipDisambiguation?, cerebrovascular?)`, `startAsk(question, skipDisambiguation?, cerebrovascular?)` — both gain a trailing optional boolean, default `false`, sent as `cerebrovascular` in the POST body.

- [ ] **Step 1: Write the failing test**

First check whether an api.ts test file already exists:

Run: `ls web/src/lib/*.test.ts 2>/dev/null || echo "none"`

If none exists, create `web/src/lib/api.test.ts`:

```typescript
// web/src/lib/api.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest"
import { askQuestion, startAsk } from "./api"

describe("Ask request bodies", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ kind: "answer" }) } as Response)))
  })

  it("askQuestion omits cerebrovascular by default", async () => {
    await askQuestion("q")
    const [, init] = (fetch as unknown as vi.Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(false)
  })

  it("askQuestion sends cerebrovascular=true when passed", async () => {
    await askQuestion("q", undefined, false, true)
    const [, init] = (fetch as unknown as vi.Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(true)
  })

  it("startAsk sends cerebrovascular=true when passed", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ job_id: "abc" }) } as Response)))
    await startAsk("q", false, true)
    const [, init] = (fetch as unknown as vi.Mock).mock.calls[0]
    const body = JSON.parse(init.body as string)
    expect(body.cerebrovascular).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- api.test.ts`
Expected: FAIL — `body.cerebrovascular` is `undefined`, not `false`/`true`

- [ ] **Step 3: Write the implementation**

Modify `web/src/lib/api.ts:107-138` from:

```typescript
export async function askQuestion(question: string, signal?: AbortSignal,
                                  skipDisambiguation = false): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, skip_disambiguation: skipDisambiguation }),
    signal,
  })
  // Every outcome (answer / clarification / unavailable / error) is a JSON body carrying `kind`,
  // even on 4xx/5xx — so we forward the engine's honest state rather than throwing.
  const data = (await res.json().catch(() => null)) as AskResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

// ----- Ask streaming (job + SSE) -------------------------------------------------------------
// startAsk creates a server-owned job (a daemon thread runs the pipeline) and returns its id.
// openAskStream replays/tails the job's SSE event log from a cursor; the caller reduces events
// into state. See askStore.ts for the event shapes and the reducer.

/** Create an Ask job; returns its id immediately (generation runs server-side). */
export async function startAsk(
  question: string,
  skipDisambiguation = false,
): Promise<{ job_id: string }> {
  const res = await fetch("/api/ask/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, skip_disambiguation: skipDisambiguation }),
  })
  return (await res.json()) as { job_id: string }
}
```

to:

```typescript
export async function askQuestion(question: string, signal?: AbortSignal,
                                  skipDisambiguation = false,
                                  cerebrovascular = false): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question, skip_disambiguation: skipDisambiguation, cerebrovascular,
    }),
    signal,
  })
  // Every outcome (answer / clarification / unavailable / error) is a JSON body carrying `kind`,
  // even on 4xx/5xx — so we forward the engine's honest state rather than throwing.
  const data = (await res.json().catch(() => null)) as AskResponse | null
  if (data && typeof data === "object" && "kind" in data) return data
  return { kind: "error", error: `Unexpected response (${res.status})` }
}

// ----- Ask streaming (job + SSE) -------------------------------------------------------------
// startAsk creates a server-owned job (a daemon thread runs the pipeline) and returns its id.
// openAskStream replays/tails the job's SSE event log from a cursor; the caller reduces events
// into state. See askStore.ts for the event shapes and the reducer.

/** Create an Ask job; returns its id immediately (generation runs server-side). */
export async function startAsk(
  question: string,
  skipDisambiguation = false,
  cerebrovascular = false,
): Promise<{ job_id: string }> {
  const res = await fetch("/api/ask/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question, skip_disambiguation: skipDisambiguation, cerebrovascular,
    }),
  })
  return (await res.json()) as { job_id: string }
}
```

Modify `web/src/pages/Ask.tsx`. Add a checkbox state near the other `useState` calls (after line 48's `netError` state):

```typescript
  const [cerebrovascular, setCerebrovascular] = useState(false)
```

Modify the `run` function (lines 76-94) from:

```typescript
  async function run(q: string, opts?: { skipDisambiguation?: boolean }) {
    const text = q.trim()
    if (!text) return
    esRef.current?.close()
    clearAsk(localStorage)
    setQuestion(text)
    setNetError(null)
    try {
      const { job_id } = await startAsk(text, opts?.skipDisambiguation ?? false)
```

to:

```typescript
  async function run(q: string, opts?: { skipDisambiguation?: boolean }) {
    const text = q.trim()
    if (!text) return
    esRef.current?.close()
    clearAsk(localStorage)
    setQuestion(text)
    setNetError(null)
    try {
      const { job_id } = await startAsk(text, opts?.skipDisambiguation ?? false, cerebrovascular)
```

Add the checkbox to the form (lines 134-153), from:

```typescript
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(question)
        }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='e.g. "blood supply of the lateral medulla"'
          className="field flex-1"
          disabled={streaming}
          autoFocus
        />
        <Button type="submit" disabled={streaming || !question.trim()} className="sm:px-7 sm:py-3">
          {streaming ? "Asking…" : "Ask"}
        </Button>
      </form>
```

to:

```typescript
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(question)
        }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='e.g. "blood supply of the lateral medulla"'
          className="field flex-1"
          disabled={streaming}
          autoFocus
        />
        <Button type="submit" disabled={streaming || !question.trim()} className="sm:px-7 sm:py-3">
          {streaming ? "Asking…" : "Ask"}
        </Button>
      </form>

      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          checked={cerebrovascular}
          onChange={(e) => setCerebrovascular(e.target.checked)}
          disabled={streaming}
        />
        Cerebrovascular question (search curated full-text literature)
      </label>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm run test -- api.test.ts && npm run lint`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/api.test.ts web/src/pages/Ask.tsx
git commit -m "feat(cv-corpus): add cerebrovascular checkbox to the Ask page"
```

---

## Task 9: Build the real corpus + smoke-test end to end

This task runs the ingestion for real (not a test) and manually verifies the whole path. No new source files.

- [ ] **Step 1: Run the ingestion script against the real data**

```bash
cd /home/michael/PROJECTS/neuro-caseboard
python scripts/build_cv_curated_corpus.py
```

Expected output: a `[done] copied=<N> extracted=<M> skipped=<K>` line where `N` is close to 354, `N+M+K` is close to 508 (`K` should be 0 or very small — every PMID in `have-list.csv` has at least a `.txt` file per the July 2026 audit). Confirm the DB exists:

```bash
ls -la ~/neuro-caseboard-corpus/fulltext/cv_curated_fulltext.sqlite
sqlite3 ~/neuro-caseboard-corpus/fulltext/cv_curated_fulltext.sqlite \
  "SELECT COUNT(*) FROM works;"
```

Expected: a row count close to 508.

- [ ] **Step 2: Build the FTS5 sidecar, reusing the existing script via env override**

```bash
CORPUS_SOURCE_DIR=~/neuro-caseboard-corpus/fulltext \
  python scripts/build_corpus_fts.py cv_curated
```

Expected: `[built] cv_curated: <N>/<N> rows in <T>s -> /home/michael/.cache/neuro_caseboard/corpus_fts/cv_curated_fts.sqlite`

- [ ] **Step 3: Manual smoke test against the running API**

Start the dev servers if not already running (`./dev.sh`), then:

```bash
curl -s -X POST http://localhost:8001/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "what is the evidence for endovascular thrombectomy in large vessel occlusion?", "cerebrovascular": true}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('kind')); print([c for c in d.get('citations', []) if str(c.get('n','')).startswith('D')] or 'no D# citations in top-level citations key — check answer text for [D#] markers'); print(d['answer'][:400] if d.get('answer') else d)"
```

Expected: `kind` is `answer`, and the answer text contains at least one `[D#]` marker (check by eye — the citations array itself only carries `[n]` textbook citations; `[D#]` sources are verified via the `corpus` field on `QAResult`, not yet surfaced in the API's JSON response body, which is fine for this task — the goal here is confirming Lane C actually returns and gets woven into the answer, not adding a new UI surface for `[D#]` sources).

- [ ] **Step 4: Confirm the flag-off path is unaffected**

```bash
curl -s -X POST http://localhost:8001/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "what is the evidence for endovascular thrombectomy in large vessel occlusion?"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('kind'))"
```

Expected: `answer` (same as before this feature — Lane C stays off by default).

- [ ] **Step 5: Commit the build/verification note**

No code changes in this task — nothing to commit unless the smoke test surfaced a bug fixed in an earlier task's file, in which case amend that task's commit per normal TDD flow (fix, add a regression test, new commit).

---

## Self-Review Notes

- **Spec coverage:** Storage (Task 5/9), ingestion reusing existing extraction (Tasks 3/5), fresh JATS/plaintext extraction (Task 1/5), per-request opt-in on both Ask endpoints (Task 6/7), web checkbox (Task 8), `[D#]` citation style reused as-is (no task needed — nothing to change), error handling / idempotency (Tasks 2/5, asserted directly in tests), out-of-scope items (other 9 subspecialties, cv-curric DB mutation, PDF-lane changes) — none touched by any task.
- **Type consistency checked:** `passages: list[tuple[str, str]]` used identically across Tasks 1/2/3/5; `CorpusConfig` field names (`enabled`, `dbs`, `source_dir`) match `neuro_caseboard/corpus.py`'s actual dataclass; `run_ask_job`'s new `corpus_config` param name matches `stream_answer`'s existing param name exactly.
- **No placeholders:** every step above has complete, runnable code — verified by re-reading each task's Step 3 for TODO/TBD markers (none found).
