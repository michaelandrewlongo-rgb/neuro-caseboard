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
