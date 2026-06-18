"""Focused tests for MCP get_fulltext handler formatting."""

from __future__ import annotations

import pytest

import caseprep.mcp_server as mcp_server
from caseprep.retrievers.fulltext import FullTextRecord


@pytest.fixture
def fake_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_pubmed_summaries(pmids: list[str]) -> list[dict[str, str]]:
        assert pmids == ["123"]
        return [
            {
                "title": "Example Title",
                "authors": "Example Authors",
                "source": "Example Journal",
                "pubdate": "2024",
            }
        ]

    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fake_pubmed_summaries)

    async def fail_helper(pmids: list[str]) -> dict:
        raise AssertionError("_handle_get_fulltext should use FullTextRetriever")

    monkeypatch.setattr(mcp_server, "_pubmed_fulltext", fail_helper)
    monkeypatch.setattr(mcp_server, "_pubmed_structured_abstracts", fail_helper)
    monkeypatch.setattr(mcp_server, "_pubmed_abstracts", fail_helper)


def _install_fake_retriever(
    monkeypatch: pytest.MonkeyPatch,
    record: FullTextRecord,
) -> list[str]:
    calls: list[str] = []

    class FakeFullTextRetriever:
        async def retrieve(self, pmid: str) -> FullTextRecord:
            calls.append(pmid)
            return record

    monkeypatch.setattr(mcp_server, "FullTextRetriever", FakeFullTextRetriever)
    return calls


@pytest.mark.asyncio
async def test_handle_get_fulltext_formats_pmc_fulltext_from_retriever(
    monkeypatch: pytest.MonkeyPatch,
    fake_summary: None,
):
    calls = _install_fake_retriever(
        monkeypatch,
        FullTextRecord(
            pmid="123",
            tier="pmc_fulltext",
            text="PMC body text",
            sections={"FULL_TEXT": "PMC body text"},
        ),
    )

    result = await mcp_server._handle_get_fulltext({"pmid": "123"})

    assert calls == ["123"]
    assert result == (
        "## Example Title\n"
        "Example Authors — *Example Journal* (2024)\n\n"
        "### PMC Full Text\n\n"
        "PMC body text"
    )


@pytest.mark.asyncio
async def test_handle_get_fulltext_formats_structured_abstract_sections_from_retriever(
    monkeypatch: pytest.MonkeyPatch,
    fake_summary: None,
):
    _install_fake_retriever(
        monkeypatch,
        FullTextRecord(
            pmid="123",
            tier="structured_abstract",
            text="Why\n\nHow\n\nUnlabeled text",
            sections={
                "BACKGROUND": "Why",
                "METHODS": "How",
                "TEXT": "Unlabeled text",
            },
        ),
    )

    result = await mcp_server._handle_get_fulltext({"pmid": "123"})

    assert result == (
        "## Example Title\n"
        "Example Authors — *Example Journal* (2024)\n\n"
        "### Structured Abstract\n\n"
        "**Background:** Why\n\n"
        "**Methods:** How\n\n"
        "Unlabeled text\n"
    )


@pytest.mark.asyncio
async def test_handle_get_fulltext_formats_plain_abstract_from_retriever(
    monkeypatch: pytest.MonkeyPatch,
    fake_summary: None,
):
    _install_fake_retriever(
        monkeypatch,
        FullTextRecord(
            pmid="123",
            tier="plain_abstract",
            text="Plain abstract text",
        ),
    )

    result = await mcp_server._handle_get_fulltext({"pmid": "123"})

    assert result == (
        "## Example Title\n"
        "Example Authors — *Example Journal* (2024)\n\n"
        "### Abstract\n\n"
        "Plain abstract text"
    )


@pytest.mark.asyncio
async def test_handle_get_fulltext_missing_preserves_no_content_message_and_adds_warning(
    monkeypatch: pytest.MonkeyPatch,
    fake_summary: None,
):
    _install_fake_retriever(
        monkeypatch,
        FullTextRecord(
            pmid="123",
            tier="missing",
            text="",
            warnings=("provider warning",),
        ),
    )

    result = await mcp_server._handle_get_fulltext({"pmid": "123"})

    assert result.startswith("No full text or abstract available for PMID 123.")
    assert "Warnings:" in result
    assert "- provider warning" in result
