"""Morning digest: the failure modes that would be silent.

The digest runs unattended at 05:30 with nobody watching, so the tests here target the
ways it could lose literature without erroring: marking papers as reported when the email
never went out, re-reporting the same paper, or truncating a topic without saying so.
"""

import datetime as _dt
import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "morning_digest.py"
_spec = importlib.util.spec_from_file_location("morning_digest", _SCRIPT)
md = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(md)


def _paper(pmid, title="A trial of something", journal="J Neurosurg"):
    return {"pmid": pmid, "title": title, "journal": journal, "pubdate": "2026 Jul",
            "authors": "Smith J, Doe A", "pub_types": ["Randomized Controlled Trial"],
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(md._SCHEMA)
    return c


# --- the PubMed window ------------------------------------------------------------------

def test_window_term_uses_entry_date_not_publication_date():
    # A paper published in 2024 but indexed last night is new to us; [PDAT] would drop it.
    term = md.window_term("cerebral vasospasm", _dt.date(2026, 7, 17))
    assert '"2026/07/17"[EDAT] : "3000"[EDAT]' in term
    assert "[PDAT]" not in term
    assert "(cerebral vasospasm)" in term          # topic stays parenthesized vs the AND


# --- dedup state ------------------------------------------------------------------------

def test_unseen_filters_only_the_same_topic(conn):
    md.mark_seen(conn, "topicA", ["111", "222"])
    assert md.unseen(conn, "topicA", ["111", "222", "333"]) == ["333"]
    assert md.unseen(conn, "topicB", ["111"]) == ["111"]   # same paper, different watch


def test_unseen_preserves_pubmed_order(conn):
    md.mark_seen(conn, "t", ["222"])
    assert md.unseen(conn, "t", ["333", "222", "111"]) == ["333", "111"]


def test_mark_seen_is_idempotent(conn):
    md.mark_seen(conn, "t", ["111"])
    md.mark_seen(conn, "t", ["111"])                       # a re-run must not raise
    assert conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0] == 1


# --- topics -----------------------------------------------------------------------------

def test_load_topics_parses_labels_and_skips_comments(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# a comment\n\nVasospasm :: cerebral vasospasm AND nimodipine\n"
                 "chronic subdural hematoma\n")
    assert md.load_topics(str(f)) == [
        ("Vasospasm", "cerebral vasospasm AND nimodipine"),
        ("chronic subdural hematoma", "chronic subdural hematoma")]


# --- build_sections ---------------------------------------------------------------------

def _stub_pubmed(monkeypatch, *, pmids, abstracts=None, papers=None):
    abstracts = abstracts if abstracts is not None else {p: f"abstract {p}" for p in pmids}
    monkeypatch.setattr(md, "esearch", lambda *a, **k: list(pmids))
    monkeypatch.setattr(md, "esummary",
                        lambda ids, **k: papers if papers is not None else [_paper(i) for i in ids])
    monkeypatch.setattr(md, "efetch_abstracts",
                        lambda ids, **k: {i: abstracts[i] for i in ids if i in abstracts})
    monkeypatch.setattr(md, "summarize", lambda *a, **k: "- finding one [L1]")
    monkeypatch.setattr(md.time, "sleep", lambda *_: None)


def test_build_sections_caps_per_topic_and_reports_the_drop(monkeypatch, conn):
    _stub_pubmed(monkeypatch, pmids=[str(i) for i in range(10)])
    (s,) = md.build_sections([("T", "q")], conn, days=7, max_per_topic=3,
                             ncbi_key="", or_key="k", model="m")
    assert len(s["papers"]) == 3
    assert s["dropped"] == 7            # surfaced, never silently swallowed


def test_papers_without_abstracts_are_dropped_but_still_marked_reported(monkeypatch, conn):
    # Nothing citable, so they can't go in the email — but they must not be re-fetched nightly.
    _stub_pubmed(monkeypatch, pmids=["1", "2"], abstracts={"1": "abstract 1"})
    (s,) = md.build_sections([("T", "q")], conn, days=7, max_per_topic=6,
                             ncbi_key="", or_key="k", model="m")
    assert [p["pmid"] for p in s["papers"]] == ["1"]
    assert s["reported"] == ["1", "2"]


def test_synthesis_outage_keeps_the_papers(monkeypatch, conn):
    _stub_pubmed(monkeypatch, pmids=["1"])
    monkeypatch.setattr(md, "summarize", lambda *a, **k: "")     # model down
    (s,) = md.build_sections([("T", "q")], conn, days=7, max_per_topic=6,
                             ncbi_key="", or_key="k", model="m")
    assert s["bullets"] == "" and len(s["papers"]) == 1
    assert "Summary unavailable" in md.render_html([s], since=_dt.date(2026, 7, 17),
                                                   generated=_dt.datetime(2026, 7, 24, 5, 30))


# --- rendering --------------------------------------------------------------------------

def test_citations_become_links_and_markup_is_escaped():
    papers = [_paper("111"), _paper("222", title="Trial of <script>alert(1)</script>")]
    out = md.render_html([{"label": "T", "papers": papers, "bullets": "- x [L2]",
                           "dropped": 0}],
                         since=_dt.date(2026, 7, 17),
                         generated=_dt.datetime(2026, 7, 24, 5, 30))
    assert 'href="https://pubmed.ncbi.nlm.nih.gov/222/"' in out
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_out_of_range_citation_is_left_alone_not_linked():
    out = md.render_html([{"label": "T", "papers": [_paper("111")], "bullets": "- x [L9]",
                           "dropped": 0}],
                         since=_dt.date(2026, 7, 17),
                         generated=_dt.datetime(2026, 7, 24, 5, 30))
    assert "[L9]" in out and "/9/" not in out


def test_empty_digest_still_renders_a_body():
    # Silence is indistinguishable from a dead cron, so a quiet day still gets an email.
    out = md.render_html([{"label": "T", "papers": [], "bullets": "", "dropped": 0}],
                         since=_dt.date(2026, 7, 17),
                         generated=_dt.datetime(2026, 7, 24, 5, 30))
    assert "No new papers" in out
    assert "nothing new" in md.render_text(
        [{"label": "T", "papers": [], "bullets": "", "dropped": 0}], since=_dt.date(2026, 7, 17))


# --- main(): the send/mark ordering -------------------------------------------------------

def _run_main(monkeypatch, tmp_path, argv, *, send=None):
    topics = tmp_path / "topics.txt"
    topics.write_text("T :: q\n")
    db = tmp_path / "digest.db"
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("DIGEST_TO", "me@example.com")
    monkeypatch.setenv("DIGEST_SMTP_USER", "me@example.com")
    monkeypatch.setenv("DIGEST_SMTP_PASS", "pw")
    sent = []
    monkeypatch.setattr(md, "send_email", send or (lambda **kw: sent.append(kw)))
    rc = md.main([*argv, "--topics", str(topics), "--db", str(db)])
    return rc, sent, db


def test_dry_run_sends_nothing_and_marks_nothing(monkeypatch, tmp_path):
    _stub_pubmed(monkeypatch, pmids=["1"])
    rc, sent, db = _run_main(monkeypatch, tmp_path, ["--dry-run"])
    assert rc == 0 and sent == []
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM seen").fetchone()[0] == 0


def test_papers_are_marked_seen_only_after_a_successful_send(monkeypatch, tmp_path):
    _stub_pubmed(monkeypatch, pmids=["1"])
    rc, sent, db = _run_main(monkeypatch, tmp_path, [])
    assert rc == 0 and len(sent) == 1
    assert sent[0]["subject"] == "Morning Rounds — 1 new paper"
    assert sqlite3.connect(db).execute(
        "SELECT pmid FROM seen").fetchone()[0] == "1"


def test_a_failed_send_does_not_swallow_the_papers(monkeypatch, tmp_path):
    """The whole point of the ordering: tomorrow must re-report what never arrived."""
    _stub_pubmed(monkeypatch, pmids=["1"])

    def boom(**kw):
        raise OSError("smtp refused")
    with pytest.raises(OSError):
        _run_main(monkeypatch, tmp_path, [], send=boom)
    db = tmp_path / "digest.db"
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM seen").fetchone()[0] == 0


def test_missing_credentials_fail_loud_before_spending_anything(monkeypatch, tmp_path):
    """Retrieval + synthesis cost ~3 min and an LLM call per topic; a missing password
    must be caught before any of that is spent, not after."""
    monkeypatch.setattr(md, "esearch", lambda *a, **k: pytest.fail("must not call PubMed"))
    monkeypatch.setattr(md, "summarize", lambda *a, **k: pytest.fail("must not call the LLM"))
    topics = tmp_path / "topics.txt"
    topics.write_text("T :: q\n")
    db = tmp_path / "digest.db"
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.delenv("DIGEST_TO", raising=False)
    monkeypatch.setenv("DIGEST_SMTP_USER", "")
    monkeypatch.setenv("DIGEST_SMTP_PASS", "")
    rc = md.main(["--topics", str(topics), "--db", str(db)])
    assert rc == 2
    assert not db.exists()          # bailed before opening state, let alone writing it


def test_no_openrouter_key_exits_before_touching_pubmed(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(md, "esearch", lambda *a, **k: pytest.fail("must not call PubMed"))
    topics = tmp_path / "topics.txt"
    topics.write_text("T :: q\n")
    assert md.main(["--topics", str(topics), "--db", str(tmp_path / "d.db")]) == 2
