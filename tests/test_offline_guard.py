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


import socket

import pytest


def test_socket_guard_blocks_loopback_connections():
    """Blocking loopback is deliberate. The 134s stall this suite suffered was a
    connect to 127.0.0.1:5432 -- a guard that only blocked external traffic would
    have missed the single worst offender."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # settimeout keeps THIS test fast before the guard exists: without it the
    # pre-guard run would itself block ~134s on the dropped-packet path.
    sock.settimeout(0.1)
    try:
        with pytest.raises(RuntimeError, match="Blocked network connection to"):
            sock.connect(("127.0.0.1", 5432))
    finally:
        sock.close()


def test_socket_guard_blocks_external_connections():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.1)
    try:
        with pytest.raises(RuntimeError, match="Blocked network connection to"):
            sock.connect(("104.18.2.115", 443))  # openrouter.ai
    finally:
        sock.close()


def test_socket_guard_blocks_connect_ex():
    """connect_ex is a distinct socket method from connect -- it reports errors via
    return code instead of an exception, so it bypasses a guard that only patches
    connect(). Unpatched, it completes a real connection attempt: verified to return
    EINPROGRESS against 127.0.0.1:5432 and, without settimeout, to incur the full
    134s SYN schedule."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.1)
    try:
        with pytest.raises(RuntimeError, match="Blocked network connection to"):
            sock.connect_ex(("127.0.0.1", 5432))
    finally:
        sock.close()


def test_socket_guard_names_the_offending_test():
    """A guard that says only "blocked" is not actionable. It must report where."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.1)
    try:
        with pytest.raises(RuntimeError) as excinfo:
            sock.connect(("127.0.0.1", 5432))
        assert "test_socket_guard_names_the_offending_test" in str(excinfo.value)
    finally:
        sock.close()
