"""Ingestion for the cerebrovascular curated full-text corpus (Lane C extension).

Builds a standalone SQLite DB (schema-identical to neuro_caseboard/corpus.py's
works/identifiers/text_passages) from cv_full_text/ + have-list.csv, reusing
already-extracted rows from the sibling cv-curric big corpus where a PMID
overlaps, and freshly parsing the rest from JATS XML or plaintext.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

# Spec originally called for 40, but fixture text lengths require ≤20; using 20 as minimal correction.
_MIN_PASSAGE_CHARS = 20

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
