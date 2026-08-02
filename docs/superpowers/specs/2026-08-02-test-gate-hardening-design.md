# Test-gate hardening — enforce the offline invariant

**Date:** 2026-08-02
**Branch:** `chore/repo-cleanup`
**Status:** design approved, implementation not started

## Problem

The test suite takes over 50 minutes and never finishes. It is not slow — it is blocked on
network connections it was never supposed to make.

`pyproject.toml` already declares the rule: *"Tests are fully offline and must stay that way."*
Nothing enforces it.

Two connections cause the entire delay:

1. **PostgreSQL, 134 seconds per attempt.**
   `vendor/caseprep/caseprep/explorer/kg_adapter.py:48-67` calls `psycopg2.connect()` with no
   `connect_timeout`, so it defers to the OS TCP stack. On this WSL2 host, packets to a closed
   5432 are dropped rather than refused, so the kernel runs its full SYN retry schedule
   (1+2+4+8+16+32+64s) before giving up. Measured: **134.1 s**.

   The failure is also not cached. Line 66 sets `_CONNECTION = None` with the comment *"so we
   don't retry every call"*, but the guard on line 48 is `if _CONNECTION is not None: return`.
   Because failure leaves it `None`, it reconnects on **every call** — the code does the
   opposite of its comment. Evidence: a live pytest process held SYN-SENT sockets on rotating
   source ports (46044, 47232, 45758) while sitting at 5-11% CPU.

   Roughly 60 tests drive a case-plan build. 60 x 134 s ~= 2.2 hours of pure waiting.

2. **Real, billed OpenRouter API calls.**
   `vendor/caseprep/caseprep/mcp_server.py:56-64` reads `~/.hermes/.env` at **module import
   time** and injects every variable into `os.environ` via `setdefault`. That file holds live
   credentials. `explorer/llm_template.py:26-33` then reads `OPENROUTER_API_KEY` into a module
   constant at import, `_llm_available()` returns True, and `build_llm_manifest()` fires a real
   API call with a 30-second timeout plus exponential retry. An ESTABLISHED TLS socket to
   `104.18.2.115:443` (openrouter.ai) was observed owned by the running pytest process.

Both go unchecked because **`tests/conftest.py` cannot reach the vendored tests.** pytest scopes
conftest by directory. `testpaths = ["tests", "vendor/caseprep/tests"]`, so all 526 vendored
tests run with zero offline protection. The caseboard side leaks too, because caseprep's
env-loading happens at import and bypasses `NEURO_CASEBOARD_SKIP_DOTENV` entirely.

### Verified baseline

```
PAPERS_CORPUS_DB_URL=disabled OPENROUTER_API_KEY= CASEPREP_LLM_KEY= python3 -m pytest -q
  -> 1577 passed, 2 skipped, 12 warnings in 89.36s
```

From >50 minutes and never completing, to 89 seconds. No test was rewritten, deleted, or marked
slow. The same 1,577 tests pass either way.

### Scope note — this is not a production latency bug

`neuro_caseboard/pipeline.py:68-72` (`_deterministic_manifest`) deliberately calls
`build_generic_manifest`, not `build_question_manifest`. Its docstring says why: *"Avoids the
KG/LLM adapters in build_question_manifest, which block on an unavailable knowledge-graph
database."* The bug was already known and routed around. `caseprep/core/builder.py` — the caller
that does reach the blocking path — is never imported by neuro-caseboard production code.

The 134-second stall therefore affects **only the 526 vendored caseprep tests**, not the running
application. Since caseprep is a candidate for absorption or deletion, the fix stays outside
vendored code so that none of this work is wasted.

## Design

One new file at the repo root, plus a two-line change in a second repository. **No vendored code
is modified.**

### Component 1 — `conftest.py` (repo root, new)

Placed at the root because that is the only location pytest imports before collecting *both*
`tests/` and `vendor/caseprep/tests/`.

**Responsibility A — neutralize credentials at module level.**

```python
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["CASEPREP_LLM_KEY"] = ""
os.environ["PAPERS_CORPUS_DB_URL"] = "disabled"
```

Module level, not an autouse fixture. This is required, not stylistic: `llm_template.py` reads
`OPENROUTER_API_KEY` into a module-level constant at import time, so a fixture runs too late to
have any effect.

A hard assignment, not `setdefault` — the inherited shell environment must be overridden.

`"disabled"` is chosen deliberately. `kg_adapter._parse_db_url` uses a regex that will not match
it, so it raises, the existing `except Exception` catches it, and the connection is never
attempted. **The failure happens at string-parse time and never opens a socket**, so it cannot
wait on TCP regardless of how the host treats dropped packets.

Empty string is correct for the API keys: `_llm_available()` returns `bool(_LLM_API_KEY.strip())`,
so `""` is falsy and the LLM path stays off.

**Responsibility B — socket guard.**

Patch `socket.socket.connect` and `socket.create_connection` to raise `RuntimeError` immediately,
naming the destination address and the test that attempted it.

Installed at **module level, alongside Responsibility A** — not in `pytest_configure` and not in a
fixture. Import-time connects happen during collection, before either of those run, and
collection is exactly when `caseprep.mcp_server` and `llm_template` get imported. Installing at
module level means the guard is armed for the entire session, collection included.

The offending test is identified from the `PYTEST_CURRENT_TEST` environment variable, which
pytest maintains for the duration of each test. During collection that variable is absent, so the
message falls back to reporting the import that triggered the connect. Both cases must produce an
actionable message; "connection blocked" with no location is not acceptable.

`socket.create_connection` is patched in addition to `socket.socket.connect` even though it calls
through to it, so that the error message can name the intended address rather than a
partially-resolved one.

**No allowlist.** Verified: no test in the suite opens a real socket. `tests/test_serve_phone.py`
only builds argv strings; the 8 `TestClient` files use in-process ASGI transport with no real
socket; `tests/test_cli_smoke.py` shells out to a subprocess, which an in-process guard does not
intercept (the subprocess inherits the neutralized environment instead).

Blocking **everything, loopback included**, is the point. The Postgres connect is to
`127.0.0.1:5432` — a conventional "block external only" guard would let the worst offender
straight through.

Without this guard, Responsibility A is a band-aid: the next test that reaches for the network
silently restores a 50-minute suite. With it, that test fails in milliseconds and says where.

**Interaction with `tests/conftest.py`:** none. That file stays untouched. It monkeypatches
different variables (`LITERATURE_RETRIEVAL`, `NEURO_CASEBOARD_SKIP_DOTENV`, `CASEBOARD_NLI_MODEL`)
per-test via fixture. The root conftest is imported first and sets different variables at module
scope. No overlap, no conflict.

### Component 2 — `bin/preflight` (repo `mac-app-hosting`, modified)

```diff
   (
     cd "$OPNOTE_SOURCE"
-    python3 -m pytest -q
+    timeout 600 python3 -m pytest -q
   )
   (
     cd "$CASEBOARD_SOURCE"
-    python3 -m pytest
+    timeout 600 python3 -m pytest
   )
```

Both invocations currently run without a timeout under `set -euo pipefail`. A hang there blocks
the deploy forever with no error and no output. A deploy gate that hangs is strictly worse than
one that fails.

This lands as its own commit in its own repository. The two repos are not otherwise entangled.

## Testing

1. **Guard fires when it should** — one small test that attempts a connect and asserts
   `RuntimeError`. This is the only new test.
2. **Suite parity** — all **1577 pre-existing tests must still pass**, with **2 skipped**,
   matching the verified baseline. The total rises only by the guard tests added alongside this
   work. A change in any *other* count means a pre-existing test changed behaviour: investigate
   it, do not adjust the expectation to match the output.
3. **Wall clock** — under 3 minutes, measured.
4. **preflight** — `bash -n bin/preflight` passes, then a real run.

### Known risk

If a test currently makes a connect that quietly succeeds or fails fast, the guard converts it
into a failure. That is the guard working, not a regression — it surfaces something currently
unknown. Any such case is reported rather than allowlisted away.

## Deliberately out of scope

Both accepted as known residual risk:

- **The credential leak is contained, not closed.** `mcp_server.py` still loads `~/.hermes/.env`
  at import for non-test processes. Impact is limited to local development — the Mac has no such
  file — but the exposure remains for any process importing that module.
- **`kg_adapter`'s inverted retry guard stays broken.** Harmless while `PAPERS_CORPUS_DB_URL` is
  neutralized and while production routes around the path, but it is a live landmine for whoever
  absorbs caseprep later. This must be carried into that project's notes.

Also out of scope, tracked separately: absorbing caseprep into `neuro_caseboard/` (11% of its
24,922 lines are live, 45% are unreachable, upstream is dead since 2026-06-12), and repointing
the Hermes MCP server off this repo's editable install.

## Non-goals

- **No pytest-xdist.** At 89 seconds, parallelism would save under a minute while introducing
  real hazards: `vendor/caseprep/tests/test_cli.py` calls bare `os.chdir()` (lines 112, 196) and
  `kg_adapter._CONNECTION` is a module-level singleton.
- **No fast/slow test split.** The premise dissolves at 89 seconds. A split would add
  configuration and a second place for coverage to rot.
- **No test rewrites.** Nothing is marked slow, skipped, or deleted.
