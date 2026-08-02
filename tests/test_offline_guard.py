"""The suite is offline by contract (pyproject.toml: "Tests are fully offline and
must stay that way"). These tests prove the contract is enforced, not just stated."""
import os


def test_llm_credentials_are_neutralized():
    """caseprep's mcp_server injects ~/.hermes/.env at import time via
    os.environ.setdefault, which would otherwise hand the suite a live
    OPENROUTER_API_KEY and cause real, billed API calls."""
    assert os.environ.get("OPENROUTER_API_KEY") == ""
    assert os.environ.get("CASEPREP_LLM_KEY") == ""


def test_kg_database_url_is_neutralized():
    """kg_adapter._parse_db_url raises ValueError on a URL its regex rejects,
    which happens before psycopg2.connect() is reached -- so a bad-format value
    cannot wait 134s on a TCP handshake."""
    assert os.environ.get("PAPERS_CORPUS_DB_URL") == "disabled"
