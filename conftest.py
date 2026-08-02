"""Repo-root pytest configuration.

This lives at the repo root rather than in tests/ because pytest scopes conftest
by directory, and ``testpaths`` spans two trees: ``tests`` and
``vendor/caseprep/tests``. A conftest under tests/ cannot reach the vendored
suite -- which is how 526 tests came to run with no offline protection at all.

Everything here runs at MODULE level, before collection. That is required, not
stylistic: caseprep's ``explorer/llm_template`` reads OPENROUTER_API_KEY into a
module-level constant at import time, so an autouse fixture would run too late.
"""
import os
import socket

# ── Credentials: neutralize before anything imports ──────────────────────────
# Hard assignment, not setdefault: the inherited shell environment must lose.
# caseprep/mcp_server.py injects ~/.hermes/.env via os.environ.setdefault at
# import time; pre-setting these keys makes that injection a no-op for them.
# "" is correct rather than deleting: llm_template._llm_available() returns
# bool(_LLM_API_KEY.strip()), so an empty string reads as "no key".
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["CASEPREP_LLM_KEY"] = ""

# "disabled" does not match kg_adapter._parse_db_url's regex, so that function
# raises ValueError and _get_connection's `except Exception` swallows it --
# psycopg2.connect() is never called, so there is no TCP handshake to wait on.
# A syntactically valid but unreachable URL would NOT be safe: it would open a
# socket and, on this host, block ~134s because packets to a closed port are
# dropped rather than refused.
os.environ["PAPERS_CORPUS_DB_URL"] = "disabled"

# ── Socket guard: the contract, enforced ─────────────────────────────────────
# Neutralizing credentials fixes today's two offenders. This stops the next one.
# Without it, any test that reaches for the network silently restores a
# 50-minute suite; with it, that test fails in milliseconds and says where.
#
# No allowlist: nothing in this suite legitimately opens a socket. Loopback is
# blocked too -- the 134s stall was a connect to 127.0.0.1:5432, which a
# "block external only" guard would have let through.
_REAL_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection


def _blocked(address):
    # PYTEST_CURRENT_TEST is set by pytest for the duration of each test. It is
    # absent during collection, which is exactly when caseprep's import-time
    # env-loading fires -- so name that case explicitly rather than reporting
    # an empty location.
    where = os.environ.get("PYTEST_CURRENT_TEST", "module import / collection")
    raise RuntimeError(
        f"Blocked network connection to {address!r} from {where}. "
        "This suite is offline by contract (see pyproject.toml). "
        "Inject a fake instead of reaching the network. If a socket is truly "
        "required, restore it explicitly in that test via conftest._REAL_CONNECT."
    )


def _guarded_connect(self, address):
    _blocked(address)


def _guarded_create_connection(address, *args, **kwargs):
    _blocked(address)


socket.socket.connect = _guarded_connect
socket.create_connection = _guarded_create_connection
