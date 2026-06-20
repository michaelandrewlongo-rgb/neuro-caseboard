"""Tests for the internal full-text retriever abstraction."""

from __future__ import annotations

import json
import sqlite3
import sys
import types
from dataclasses import FrozenInstanceError, is_dataclass

import pytest

import caseprep.retrievers.fulltext as fulltext_module
from caseprep.retrievers.fulltext import FullTextRecord, FullTextRetriever


def _install_fake_mcp_server(monkeypatch: pytest.MonkeyPatch, **helpers: object) -> None:
    fake_module = types.ModuleType("caseprep.mcp_server")
    for name, helper in helpers.items():
        setattr(fake_module, name, helper)
    monkeypatch.setitem(sys.modules, "caseprep.mcp_server", fake_module)


@pytest.mark.asyncio
async def test_default_pubmed_providers_lazily_import_mcp_helpers(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, list[str]]] = []
    retriever = FullTextRetriever()

    def fake_fulltext(pmids: list[str]) -> dict[str, str]:
        calls.append(("fulltext", pmids))
        return {}

    def fake_structured(pmids: list[str]) -> dict[str, dict[str, str]]:
        calls.append(("structured", pmids))
        return {}

    def fake_plain(pmids: list[str]) -> dict[str, str]:
        calls.append(("plain", pmids))
        return {"111": "Plain abstract from lazy import"}

    _install_fake_mcp_server(
        monkeypatch,
        _pubmed_fulltext=fake_fulltext,
        _pubmed_structured_abstracts=fake_structured,
        _pubmed_abstracts=fake_plain,
    )

    record = await retriever.retrieve("111")

    assert record.tier == "plain_abstract"
    assert record.text == "Plain abstract from lazy import"
    assert calls == [
        ("fulltext", ["111"]),
        ("structured", ["111"]),
        ("plain", ["111"]),
    ]


@pytest.mark.asyncio
async def test_default_pmc_fulltext_wrapper_maps_dict_output_to_pmc_record(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    def fake_fulltext(pmids: list[str]) -> dict[str, object]:
        calls.append("fulltext")
        return {
            "222": {
                "text": "PMC full text from helper",
                "pmcid": "PMC222",
                "metadata": {"license": "CC-BY"},
            }
        }

    def fake_structured(pmids: list[str]) -> dict[str, dict[str, str]]:
        calls.append("structured")
        return {"222": {"RESULTS": "Structured should not win"}}

    def fake_plain(pmids: list[str]) -> dict[str, str]:
        calls.append("plain")
        return {"222": "Plain should not win"}

    _install_fake_mcp_server(
        monkeypatch,
        _pubmed_fulltext=fake_fulltext,
        _pubmed_structured_abstracts=fake_structured,
        _pubmed_abstracts=fake_plain,
    )

    record = await FullTextRetriever().retrieve("222")

    assert calls == ["fulltext"]
    assert record.tier == "pmc_fulltext"
    assert record.text == "PMC full text from helper"
    assert record.sections == {"FULL_TEXT": "PMC full text from helper"}
    assert record.metadata == {"license": "CC-BY", "pmcid": "PMC222"}
    assert record.warnings == ()


@pytest.mark.asyncio
async def test_default_fulltext_helper_exception_warns_and_structured_fallback_wins(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    def fake_fulltext(pmids: list[str]) -> dict[str, str]:
        calls.append("fulltext")
        raise RuntimeError("PMC helper down")

    def fake_structured(pmids: list[str]) -> dict[str, dict[str, str]]:
        calls.append("structured")
        return {"333": {"CONCLUSIONS": "Structured fallback from helper"}}

    def fake_plain(pmids: list[str]) -> dict[str, str]:
        calls.append("plain")
        return {"333": "Plain should not be needed"}

    _install_fake_mcp_server(
        monkeypatch,
        _pubmed_fulltext=fake_fulltext,
        _pubmed_structured_abstracts=fake_structured,
        _pubmed_abstracts=fake_plain,
    )

    record = await FullTextRetriever().retrieve("333")

    assert calls == ["fulltext", "structured"]
    assert record.tier == "structured_abstract"
    assert record.sections == {"CONCLUSIONS": "Structured fallback from helper"}
    assert len(record.warnings) == 1
    assert "pmc_fulltext provider failed" in record.warnings[0]
    assert "PMC helper down" in record.warnings[0]


@pytest.mark.asyncio
async def test_default_pubmed_provider_priority_remains_pmc_structured_plain(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    async def fake_fulltext(pmids: list[str]) -> dict[str, str]:
        calls.append("fulltext")
        return {"444": "PMC wins from helper"}

    async def fake_structured(pmids: list[str]) -> dict[str, dict[str, str]]:
        calls.append("structured")
        return {"444": {"RESULTS": "Structured should not win"}}

    async def fake_plain(pmids: list[str]) -> dict[str, str]:
        calls.append("plain")
        return {"444": "Plain should not win"}

    _install_fake_mcp_server(
        monkeypatch,
        _pubmed_fulltext=fake_fulltext,
        _pubmed_structured_abstracts=fake_structured,
        _pubmed_abstracts=fake_plain,
    )

    record = await FullTextRetriever().retrieve("444")

    assert calls == ["fulltext"]
    assert record.tier == "pmc_fulltext"
    assert record.text == "PMC wins from helper"


@pytest.mark.asyncio
async def test_pmc_fulltext_wins_over_structured_and_plain_with_plan_fields():
    calls: list[str] = []

    def pmc_provider(pmid: str) -> dict:
        calls.append("pmc")
        assert pmid == "12345"
        return {
            "title": "Full text title",
            "pmcid": "PMC12345",
            "doi": "10.1000/example",
            "sections": [
                {"label": "Introduction", "text": "Intro text"},
                {"label": "Results", "text": "Results text"},
            ],
            "metadata": {"license": "CC-BY"},
        }

    def structured_provider(pmid: str) -> dict:
        calls.append("structured")
        return {"BACKGROUND": "Should not be used"}

    def plain_provider(pmid: str) -> dict:
        calls.append("plain")
        return {"abstract": "Should not be used"}

    record = await FullTextRetriever(
        pmc_fulltext_provider=pmc_provider,
        structured_abstract_provider=structured_provider,
        plain_abstract_provider=plain_provider,
    ).retrieve("12345")

    assert calls == ["pmc"]
    assert is_dataclass(record)
    assert record.tier == "pmc_fulltext"
    assert record.source == "pmc_fulltext"  # Backward-compatible alias.
    assert record.pmid == "12345"
    assert record.text == "Intro text\n\nResults text"
    assert record.sections == {
        "Introduction": "Intro text",
        "Results": "Results text",
    }
    assert record.metadata == {
        "license": "CC-BY",
        "title": "Full text title",
        "pmcid": "PMC12345",
        "doi": "10.1000/example",
    }
    assert record.warnings == ()
    with pytest.raises(FrozenInstanceError):
        record.tier = "missing"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_structured_abstract_wins_over_plain_when_pmc_unavailable():
    async def pmc_provider(pmid: str) -> None:
        return None

    def structured_provider(pmid: str) -> dict[str, str]:
        return {"BACKGROUND": "Why", "METHODS": "How", "RESULTS": "What"}

    def plain_provider(pmid: str) -> dict[str, str]:
        return {"abstract": "Should not be used"}

    record = await FullTextRetriever(
        pmc_fulltext_provider=pmc_provider,
        structured_abstract_provider=structured_provider,
        plain_abstract_provider=plain_provider,
    ).retrieve("23456")

    assert record.tier == "structured_abstract"
    assert record.text == "Why\n\nHow\n\nWhat"
    assert record.sections == {
        "BACKGROUND": "Why",
        "METHODS": "How",
        "RESULTS": "What",
    }
    assert record.metadata == {}
    assert record.warnings == ()


@pytest.mark.asyncio
async def test_structured_abstract_accepts_unlabeled_text_section():
    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {
            pmid: {"TEXT": "Unlabeled abstract text."}
        },
        plain_abstract_provider=lambda pmid: {"abstract": "Should not be used"},
    ).retrieve("24680")

    assert record.tier == "structured_abstract"
    assert "Unlabeled abstract text." in record.text
    assert record.sections == {"TEXT": "Unlabeled abstract text."}


@pytest.mark.asyncio
async def test_plain_abstract_returned_when_only_plain_exists():
    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: {},
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: {"abstract": "Plain abstract text"},
    ).retrieve("34567")

    assert record.tier == "plain_abstract"
    assert record.text == "Plain abstract text"
    assert record.abstract == "Plain abstract text"  # Backward-compatible alias.
    assert record.sections == {}
    assert record.warnings == ()


@pytest.mark.asyncio
async def test_missing_requested_pmid_in_batch_result_falls_back_to_next_provider():
    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {"999": {"BACKGROUND": "Other PMID"}},
        plain_abstract_provider=lambda pmid: {"abstract": "Requested abstract"},
    ).retrieve("123")

    assert record.tier == "plain_abstract"
    assert record.pmid == "123"
    assert record.text == "Requested abstract"
    assert record.sections == {}


@pytest.mark.asyncio
async def test_provider_exception_is_tuple_warning_and_fallback_still_works():
    def broken_pmc_provider(pmid: str) -> dict:
        raise RuntimeError("PMC is down")

    record = await FullTextRetriever(
        pmc_fulltext_provider=broken_pmc_provider,
        structured_abstract_provider=lambda pmid: {"CONCLUSIONS": "Fallback worked"},
    ).retrieve("45678")

    assert record.tier == "structured_abstract"
    assert record.sections == {"CONCLUSIONS": "Fallback worked"}
    assert isinstance(record.warnings, tuple)
    assert len(record.warnings) == 1
    assert "pmc_fulltext" in record.warnings[0]
    assert "PMC is down" in record.warnings[0]


@pytest.mark.asyncio
async def test_all_empty_returns_missing_with_warning_without_crashing():
    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
        local_fulltext_provider=lambda pmid: None,
    ).retrieve("56789")

    assert record == FullTextRecord(
        pmid="56789",
        tier="missing",
        text="",
        sections={},
        metadata={},
        warnings=("No full text or abstract available for PMID",),
    )


@pytest.mark.asyncio
async def test_sync_and_async_injected_fetchers_and_local_fulltext_provider_work():
    async def async_empty_provider(pmid: str) -> None:
        return None

    def sync_empty_provider(pmid: str) -> dict[str, str]:
        return {}

    async def async_plain_empty_provider(pmid: str) -> str:
        return ""

    def local_provider(pmid: str) -> dict[str, object]:
        return {
            "sections": {"Local section": "Local full text"},
            "metadata": {"work_id": "local-1"},
        }

    record = await FullTextRetriever(
        pmc_fulltext_provider=async_empty_provider,
        structured_abstract_provider=sync_empty_provider,
        plain_abstract_provider=async_plain_empty_provider,
        local_fulltext_provider=local_provider,
    ).retrieve("67890")

    assert record.tier == "local_fulltext"
    assert record.text == "Local full text"
    assert record.sections == {"Local section": "Local full text"}
    assert record.metadata == {"work_id": "local-1"}
    assert record.warnings == ()


def _create_local_fulltext_db(db_path, *, with_expected_schema: bool = True) -> None:
    with sqlite3.connect(db_path) as conn:
        if with_expected_schema:
            conn.execute(
                """
                CREATE TABLE fulltext_records(
                    pmid TEXT PRIMARY KEY,
                    title TEXT,
                    text TEXT,
                    sections_json TEXT,
                    pmcid TEXT,
                    doi TEXT
                )
                """
            )
        else:
            conn.execute("CREATE TABLE unrelated_records(id TEXT PRIMARY KEY, body TEXT)")


def _create_nsgy_fulltext_db(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE works(
                id TEXT PRIMARY KEY,
                title TEXT,
                pub_year INTEGER,
                journal_title TEXT,
                abstract TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE identifiers(
                id TEXT PRIMARY KEY,
                work_id TEXT,
                scheme TEXT,
                value TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE text_passages(
                id TEXT PRIMARY KEY,
                work_id TEXT,
                section_type TEXT,
                content TEXT,
                sequence_number INTEGER
            )
            """
        )


@pytest.mark.asyncio
async def test_local_fulltext_db_returns_record_when_pubmed_tiers_unavailable(tmp_path):
    db_path = tmp_path / "fulltext.sqlite"
    _create_local_fulltext_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fulltext_records(pmid, title, text, sections_json, pmcid, doi)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "777",
                "Local database title",
                "Fallback full text column",
                json.dumps({"INTRO": "Local intro", "RESULTS": "Local results"}),
                "PMC777",
                "10.1000/local",
            ),
        )

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
        fulltext_db=db_path,
    ).retrieve("777")

    assert record.tier == "local_fulltext"
    assert record.text == "Local intro\n\nLocal results"
    assert record.sections == {"INTRO": "Local intro", "RESULTS": "Local results"}
    assert record.metadata == {
        "title": "Local database title",
        "pmcid": "PMC777",
        "doi": "10.1000/local",
        "source": "local_fulltext_db",
    }
    assert record.warnings == ()


@pytest.mark.asyncio
async def test_local_fulltext_db_supports_nsgy_works_identifiers_passages_schema(tmp_path):
    db_path = tmp_path / "nsgy-fulltext.sqlite"
    _create_nsgy_fulltext_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO works(id, title, pub_year, journal_title, abstract)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "work-777",
                "NSGY local database title",
                2024,
                "Journal of Local Fulltext",
                "Structured abstract lives on works.",
            ),
        )
        conn.executemany(
            "INSERT INTO identifiers(id, work_id, scheme, value) VALUES (?, ?, ?, ?)",
            [
                ("id-pmid", "work-777", "pmid", "777"),
                ("id-doi", "work-777", "doi", "10.1000/nsgy-local"),
                ("id-pmcid", "work-777", "pmcid", "PMC777"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO text_passages(id, work_id, section_type, content, sequence_number)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("p1", "work-777", "introduction", "NSGY intro passage", 1),
                ("p2", "work-777", "results", "NSGY first result", 2),
                ("p3", "work-777", "results", "NSGY second result", 3),
            ],
        )

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
        fulltext_db=db_path,
    ).retrieve("777")

    assert record.tier == "local_fulltext"
    assert record.text == "NSGY intro passage\n\nNSGY first result\n\nNSGY second result"
    assert record.sections == {
        "introduction": "NSGY intro passage",
        "results": "NSGY first result\n\nNSGY second result",
    }
    assert record.metadata["title"] == "NSGY local database title"
    assert record.metadata["work_id"] == "work-777"
    assert record.metadata["source_path"] == str(db_path)
    assert record.metadata["schema"] == "works/identifiers/text_passages"
    assert record.metadata["abstract"] == "Structured abstract lives on works."
    assert record.metadata["year"] == 2024
    assert record.metadata["journal"] == "Journal of Local Fulltext"
    assert record.metadata["doi"] == "10.1000/nsgy-local"
    assert record.metadata["pmcid"] == "PMC777"
    assert record.metadata["source"] == "local_fulltext_db"
    assert record.warnings == ()


@pytest.mark.asyncio
async def test_local_fulltext_db_supports_nsgy_works_pmid_column_fallback(tmp_path):
    db_path = tmp_path / "nsgy-fulltext-works-pmid.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE works(id TEXT PRIMARY KEY, title TEXT, pmid TEXT)")
        conn.execute(
            """
            CREATE TABLE text_passages(
                id TEXT PRIMARY KEY,
                work_id TEXT,
                section_type TEXT,
                content TEXT,
                sequence_number INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO works(id, title, pmid) VALUES (?, ?, ?)",
            ("work-778", "Works PMID fallback title", "778"),
        )
        conn.execute(
            """
            INSERT INTO text_passages(id, work_id, section_type, content, sequence_number)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("p1", "work-778", "conclusion", "Works PMID fallback passage", 1),
        )

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
        fulltext_db=db_path,
    ).retrieve("778")

    assert record.tier == "local_fulltext"
    assert record.sections == {"conclusion": "Works PMID fallback passage"}
    assert record.metadata["work_id"] == "work-778"
    assert record.metadata["title"] == "Works PMID fallback title"


@pytest.mark.asyncio
async def test_local_fulltext_db_connection_closed_per_lookup(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / "fulltext.sqlite"
    db_path.touch()
    connect_calls: list[tuple[str, bool]] = []
    close_calls: list[bool] = []

    class FakeCursor:
        def fetchone(self) -> dict[str, object]:
            return {
                "title": "Closed local title",
                "text": "Fallback local text",
                "sections_json": json.dumps({"BODY": "Closed local body"}),
                "pmcid": None,
                "doi": None,
            }

    class FakeConnection:
        row_factory = None

        def execute(self, sql: str, params: tuple[str]) -> FakeCursor:
            assert "FROM fulltext_records" in sql
            assert params == ("783",)
            return FakeCursor()

        def close(self) -> None:
            close_calls.append(True)

    def fake_connect(database: str, *, uri: bool = False) -> FakeConnection:
        connect_calls.append((database, uri))
        return FakeConnection()

    monkeypatch.setattr(fulltext_module.sqlite3, "connect", fake_connect)

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
        fulltext_db=db_path,
    ).retrieve("783")

    assert record.tier == "local_fulltext"
    assert record.text == "Closed local body"
    assert connect_calls == [(fulltext_module._sqlite_readonly_uri(db_path), True)]
    assert close_calls == [True]


@pytest.mark.asyncio
async def test_local_fulltext_db_is_supplemental_after_plain_abstract(tmp_path):
    """Document chosen order: PMC > structured > plain > local_fulltext > missing."""
    db_path = tmp_path / "fulltext.sqlite"
    _create_local_fulltext_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO fulltext_records(pmid, title, text) VALUES (?, ?, ?)",
            ("778", "Local title", "Local text should not beat plain"),
        )

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: {"abstract": "Plain abstract wins"},
        fulltext_db=db_path,
    ).retrieve("778")

    assert record.tier == "plain_abstract"
    assert record.text == "Plain abstract wins"
    assert record.warnings == ()


@pytest.mark.asyncio
async def test_missing_local_fulltext_db_path_warns_and_plain_fallback_wins(tmp_path):
    missing_db_path = tmp_path / "missing.sqlite"

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: {"abstract": "Plain fallback"},
        fulltext_db=missing_db_path,
    ).retrieve("779")

    assert record.tier == "plain_abstract"
    assert record.text == "Plain fallback"
    assert len(record.warnings) == 1
    assert "local fulltext DB path does not exist" in record.warnings[0]
    assert str(missing_db_path) in record.warnings[0]


@pytest.mark.asyncio
async def test_local_fulltext_db_schema_mismatch_warns_and_falls_through(tmp_path):
    db_path = tmp_path / "wrong-schema.sqlite"
    _create_local_fulltext_db(db_path, with_expected_schema=False)

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
        fulltext_db=db_path,
    ).retrieve("780")

    assert record.tier == "missing"
    assert any("local fulltext DB schema mismatch" in warning for warning in record.warnings)
    assert record.warnings[-1] == "No full text or abstract available for PMID"


@pytest.mark.asyncio
async def test_local_fulltext_db_env_var_used_when_constructor_arg_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    db_path = tmp_path / "env-fulltext.sqlite"
    _create_local_fulltext_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO fulltext_records(pmid, title, text) VALUES (?, ?, ?)",
            ("781", "Env local title", "Env local full text"),
        )
    monkeypatch.setenv("CASEPREP_FULLTEXT_DB", str(db_path))

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: "",
    ).retrieve("781")

    assert record.tier == "local_fulltext"
    assert record.text == "Env local full text"
    assert record.sections == {"FULL_TEXT": "Env local full text"}
    assert record.metadata["title"] == "Env local title"


@pytest.mark.asyncio
async def test_default_missing_local_fulltext_db_does_not_block_pubmed_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("CASEPREP_FULLTEXT_DB", raising=False)

    record = await FullTextRetriever(
        pmc_fulltext_provider=lambda pmid: None,
        structured_abstract_provider=lambda pmid: {},
        plain_abstract_provider=lambda pmid: {"abstract": "Plain without local DB"},
        fulltext_db=None,
    ).retrieve("782")

    assert record.tier == "plain_abstract"
    assert record.text == "Plain without local DB"
    assert record.warnings == ()


def test_to_dict_is_json_serializable_plan_shape():
    record = FullTextRecord(
        pmid="67890",
        tier="pmc_fulltext",
        text="Text",
        sections={"Body": "Text"},
        metadata={
            "title": "Serializable record",
            "pmcid": "PMC67890",
            "doi": "10.1000/serializable",
            "numbers": [1, 2, 3],
        },
        warnings=("warning",),
    )

    payload = record.to_dict()

    assert payload == {
        "pmid": "67890",
        "tier": "pmc_fulltext",
        "text": "Text",
        "sections": {"Body": "Text"},
        "metadata": {
            "title": "Serializable record",
            "pmcid": "PMC67890",
            "doi": "10.1000/serializable",
            "numbers": [1, 2, 3],
        },
        "warnings": ["warning"],
    }
    json.dumps(payload)
