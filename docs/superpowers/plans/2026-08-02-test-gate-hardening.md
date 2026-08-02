# Test-Gate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the test suite enforce its own declared offline invariant, taking it from >50 minutes-and-never-finishing to under 3 minutes, without touching vendored code.

**Architecture:** A single new `conftest.py` at the repo root does two things at module level (before pytest collects anything): it overwrites three credential/DB environment variables, and it replaces `socket.socket.connect` / `socket.create_connection` with functions that raise. Root placement is load-bearing — pytest scopes conftest by directory, and `testpaths` spans both `tests/` and `vendor/caseprep/tests/`, so the existing `tests/conftest.py` structurally cannot protect the vendored suite. Separately, `bin/preflight` in the `mac-app-hosting` repo gets a timeout so a hang fails instead of blocking deploys forever.

**Tech Stack:** Python 3.12, pytest (`--strict-markers --strict-config`), stdlib `os` and `socket` only. No new dependencies.

## Global Constraints

- Work on branch `chore/repo-cleanup` in `/home/michael/PROJECTS/neuro-caseboard`. Verify with `git branch --show-current` immediately before every commit.
- **Do not modify any file under `vendor/`.** The whole point of this design is that nothing is wasted if caseprep is later absorbed or deleted.
- **Do not modify `tests/conftest.py`.** It handles different variables by a different mechanism and does not conflict.
- Suite parity: all **1577 pre-existing tests must still pass**, with **2 skipped**. The total grows only by the guard tests this plan adds — 1579 after Task 1, 1582 after Task 2. Any *other* number means a pre-existing test changed behaviour: investigate, do not adjust the expectation to match.
- Wall clock for the full suite must be under 3 minutes.
- `pyproject.toml` sets `--strict-markers --strict-config`; any new marker must be registered or the run errors.
- No new third-party dependency may be added.
- Task 3 is in a **different repository** (`/home/michael/mac-app-hosting`) and gets its own commit there.

---

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `conftest.py` (create) | neuro-caseboard | Repo-root pytest config. Neutralizes credentials and installs the socket guard, both at module level. |
| `tests/test_offline_guard.py` (create) | neuro-caseboard | Proves the guard and the env neutralization actually work. The only new test file. |
| `bin/preflight` (modify, lines 13-20) | mac-app-hosting | Deploy gate. Gains a timeout on both pytest invocations. |

Everything lives in one new file plus one new test because the two responsibilities share a single hard requirement — they must run before collection — and splitting them across files would obscure that.

---

### Task 1: Neutralize credentials at the repo root

**Files:**
- Create: `/home/michael/PROJECTS/neuro-caseboard/conftest.py`
- Test: `/home/michael/PROJECTS/neuro-caseboard/tests/test_offline_guard.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a repo-root `conftest.py` module whose import sets `OPENROUTER_API_KEY=""`, `CASEPREP_LLM_KEY=""`, and `PAPERS_CORPUS_DB_URL="disabled"` in `os.environ`. Task 2 appends the socket guard to this same file.

**Why module level and not a fixture:** `vendor/caseprep/caseprep/explorer/llm_template.py:26-31` reads `OPENROUTER_API_KEY` into the module-level constant `_LLM_API_KEY` at import time. An autouse fixture runs after that import, so it would have no effect. This is a correctness requirement, not a style preference.

- [ ] **Step 1: Write the failing test**

Create `tests/test_offline_guard.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && python3 -m pytest tests/test_offline_guard.py -v`

Expected: both tests FAIL. `OPENROUTER_API_KEY` will be `None` (or a live key inherited from the shell); `PAPERS_CORPUS_DB_URL` will be `None`.

- [ ] **Step 3: Write minimal implementation**

Create `conftest.py` at the repo root:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && python3 -m pytest tests/test_offline_guard.py -v`

Expected: 2 passed.

- [ ] **Step 5: Verify the actual payoff — full suite time**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && time python3 -m pytest -q -p no:cacheprovider`

Expected: **1579 passed, 2 skipped** (1577 baseline + the 2 new tests) in under 3 minutes.

If the count differs from 1579/2, stop and investigate before continuing. Do not adjust the expected number to match the output.

- [ ] **Step 6: Commit**

```bash
cd /home/michael/PROJECTS/neuro-caseboard
git branch --show-current   # must print: chore/repo-cleanup
git add conftest.py tests/test_offline_guard.py
git commit -m "test: neutralize credentials at repo root so the offline contract holds

pyproject declares "Tests are fully offline and must stay that way" but nothing
enforced it. tests/conftest.py cannot -- pytest scopes conftest by directory and
testpaths spans vendor/caseprep/tests too, so 526 tests ran unprotected.

Set at module level, not in a fixture: llm_template reads OPENROUTER_API_KEY into
a module constant at import, so a fixture runs too late to matter."
```

---

### Task 2: Add the socket guard

**Files:**
- Modify: `/home/michael/PROJECTS/neuro-caseboard/conftest.py` (append after the env block from Task 1)
- Modify: `/home/michael/PROJECTS/neuro-caseboard/tests/test_offline_guard.py` (append)

**Interfaces:**
- Consumes: the `conftest.py` created in Task 1.
- Produces: `socket.socket.connect` and `socket.create_connection` replaced by functions that raise `RuntimeError` whose message begins with `"Blocked network connection to "`. The test in this task matches on that prefix, so it must not be reworded without updating the test.

**Why no allowlist:** no test in the suite opens a real socket. `tests/test_serve_phone.py` only builds argv strings; the 8 files using `TestClient` use in-process ASGI transport; `tests/test_cli_smoke.py` shells out to a subprocess, which an in-process patch does not intercept (that subprocess inherits the neutralized environment instead). Blocking loopback as well as external traffic is the entire point — the worst offender is `127.0.0.1:5432`, which a conventional "block external only" guard would allow through.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_offline_guard.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && python3 -m pytest tests/test_offline_guard.py -v`

Expected: the 3 new tests FAIL fast (well under 1 second each, thanks to `settimeout(0.1)`). They fail with `DID NOT RAISE RuntimeError` or with a `socket.timeout`/`ConnectionRefusedError` — which are `OSError` subclasses and therefore not caught by `pytest.raises(RuntimeError)`. The 2 tests from Task 1 still pass.

- [ ] **Step 3: Write minimal implementation**

Two edits to `conftest.py`. First, add `socket` to the imports at the top of the file so it reads:

```python
import os
import socket
```

Then append the guard block to the end of the file:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && python3 -m pytest tests/test_offline_guard.py -v`

Expected: 5 passed.

- [ ] **Step 5: Verify the guard did not break the rest of the suite**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && time python3 -m pytest -q -p no:cacheprovider`

Expected: **1582 passed, 2 skipped** (1577 baseline + 5 new tests) in under 3 minutes.

**This is the step most likely to surface something.** If any pre-existing test now fails with `Blocked network connection to ...`, that is the guard working — it has found a test that was quietly using the network. Do not allowlist it and do not delete the guard. Record the test name and the address, report it, and stop for a decision.

- [ ] **Step 6: Commit**

```bash
cd /home/michael/PROJECTS/neuro-caseboard
git branch --show-current   # must print: chore/repo-cleanup
git add conftest.py tests/test_offline_guard.py
git commit -m "test: block all sockets during tests so the offline contract cannot rot

Neutralized credentials fix today's two offenders; this stops the next one.
No allowlist -- nothing in the suite opens a real socket, and loopback is
blocked deliberately because the 134s stall was 127.0.0.1:5432."
```

---

### Task 3: Give the deploy gate a timeout

**Files:**
- Modify: `/home/michael/mac-app-hosting/bin/preflight:13-20`

**Interfaces:**
- Consumes: nothing from Tasks 1-2. Independently valuable — do it even if the others are reverted.
- Produces: nothing consumed by later tasks.

**Note:** different repository. Commit there, not in neuro-caseboard.

- [ ] **Step 1: Confirm the current state**

Run: `sed -n '13,20p' /home/michael/mac-app-hosting/bin/preflight`

Expected output:

```
(
  cd "$OPNOTE_SOURCE"
  python3 -m pytest -q
)
(
  cd "$CASEBOARD_SOURCE"
  python3 -m pytest
)
```

Neither invocation has a timeout. Under `set -euo pipefail` (line 2), a hang blocks the deploy forever with no error and no output.

- [ ] **Step 2: Apply the change**

Edit `/home/michael/mac-app-hosting/bin/preflight` so lines 13-20 read:

```bash
(
  cd "$OPNOTE_SOURCE"
  timeout 600 python3 -m pytest -q
)
(
  cd "$CASEBOARD_SOURCE"
  timeout 600 python3 -m pytest
)
```

600 seconds is deliberately generous — the suite now runs in ~90 seconds, so a 10-minute ceiling only fires on a genuine hang, never on ordinary slowness.

- [ ] **Step 3: Verify the script still parses**

Run: `bash -n /home/michael/mac-app-hosting/bin/preflight && echo "syntax OK"`

Expected: `syntax OK`

- [ ] **Step 4: Verify the timeout actually fires**

Run: `timeout 600 sleep 2; echo "exit=$?"` then `timeout 1 sleep 5; echo "exit=$?"`

Expected: first prints `exit=0`; second prints `exit=124`. This confirms `timeout` is present on this system and returns 124 on expiry, which is what makes preflight exit non-zero under `set -e` instead of hanging.

- [ ] **Step 5: Commit**

```bash
cd /home/michael/mac-app-hosting
git branch --show-current   # must print: main
git add bin/preflight
git commit -m "fix: bound preflight's pytest runs so a hang fails instead of blocking deploys

Both pytest invocations ran with no timeout under set -euo pipefail, so a
hanging test blocked the deploy gate forever with no error and no output.
The caseboard suite hung exactly this way for >50 min. A gate that hangs is
strictly worse than one that fails."
```

---

## Final Verification

- [ ] **Full suite, timed, from a clean shell**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && time python3 -m pytest -q -p no:cacheprovider`

Expected: **1582 passed, 2 skipped**, under 3 minutes.

- [ ] **Confirm no vendored file was touched**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && git diff --stat 4548ea9 HEAD -- vendor/`

`4548ea9` is the branch head immediately before Task 1 (the plan's own commit). Pin it
explicitly rather than counting back with `~N` — the commit count varies with how many fix
rounds each task needed, so a relative ref would silently check the wrong range.

Expected: empty output. If anything appears, a global constraint was violated.

- [ ] **Confirm the deployed pin never moved**

Run: `cd /home/michael/PROJECTS/neuro-caseboard && git rev-parse fix/step0-live-bugs`

Expected: `1c07916080a8ed317d2a7e01aebda9269a862c09`

- [ ] **Prove the guard catches a real regression**

Temporarily add a test that does `socket.create_connection(("1.1.1.1", 80))`, run it, confirm it fails with `Blocked network connection to`, then delete it. This verifies the guard against `create_connection` specifically, which the Task 2 tests exercise only via `socket.connect`.
