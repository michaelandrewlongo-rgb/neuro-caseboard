"""Live LLM call telemetry: every synthesis call records model/tokens/cost/latency/route
to a local SQLite DB, so cost and latency drag can be sliced after the fact
(see scripts/telemetry_report.py). Stdlib only — no new dependency for a handful of
inserts/second at this app's request volume."""

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

_log = logging.getLogger(__name__)

DB_PATH = os.environ.get("TELEMETRY_DB",
                          str(Path.home() / ".neuro-caseboard" / "telemetry.db"))
_PRICES_PATH = Path(__file__).with_name("telemetry_prices.json")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    ts REAL, route TEXT, provider TEXT, model TEXT,
    tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
    latency_ms REAL, ok INTEGER, error TEXT
)
"""

_warned_models = set()


def _load_prices():
    try:
        with open(_PRICES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _cost_usd(provider, model, tokens_in, tokens_out):
    if tokens_in is None or tokens_out is None:
        return None
    prices = _load_prices()
    entry = prices.get(model)
    if not entry or "in_per_1m" not in entry or "out_per_1m" not in entry:
        key = (provider, model)
        if key not in _warned_models:
            _warned_models.add(key)
            _log.warning("telemetry: no verified price for model %r (provider %s) in "
                         "%s — cost_usd will be null for this model until added.",
                         model, provider, _PRICES_PATH.name)
        return None
    return (tokens_in / 1_000_000) * entry["in_per_1m"] + \
           (tokens_out / 1_000_000) * entry["out_per_1m"]


def _write(row):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        conn.execute(
            "INSERT INTO llm_calls (ts, route, provider, model, tokens_in, tokens_out, "
            "cost_usd, latency_ms, ok, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
            row)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def track(route, provider, model):
    """Usage: `with telemetry.track(route, provider, model) as t: ... t["tokens_in"] = n`.
    Records latency/cost/error automatically; exceptions are logged then re-raised."""
    t0 = time.time()
    ctx = {"tokens_in": None, "tokens_out": None}
    ok, error = True, None
    try:
        yield ctx
    except Exception as exc:
        ok = False
        error = f"{type(exc).__name__}: {str(exc)[:400]}"
        raise
    finally:
        latency_ms = (time.time() - t0) * 1000
        cost = _cost_usd(provider, model, ctx["tokens_in"], ctx["tokens_out"])
        try:
            _write((time.time(), route, provider, model, ctx["tokens_in"],
                    ctx["tokens_out"], cost, latency_ms, int(ok), error))
        except Exception:
            _log.exception("telemetry: failed to write llm_calls row (route=%s)", route)
