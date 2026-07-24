#!/usr/bin/env python3
"""Summarize neuro_core/telemetry.py's llm_calls table: cost/tokens/latency/errors by
model, route, and day. Usage: python scripts/telemetry_report.py [--since DAYS]"""

import argparse
import sqlite3
import sys
import time

from neuro_core.telemetry import DB_PATH


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * p))
    return sorted_vals[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=float, default=None, help="only calls in the last N days")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    where, params = "", ()
    if args.since is not None:
        where = "WHERE ts >= ?"
        params = (time.time() - args.since * 86400,)

    rows = conn.execute(f"SELECT * FROM llm_calls {where} ORDER BY ts", params).fetchall()
    if not rows:
        print(f"No telemetry rows in {DB_PATH}" + (f" (last {args.since}d)" if args.since else ""))
        return

    total_cost = sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None)
    unpriced = sorted({r["model"] for r in rows if r["cost_usd"] is None})
    errors = [r for r in rows if not r["ok"]]

    print(f"DB: {DB_PATH}")
    print(f"Calls: {len(rows)}   Errors: {len(errors)} ({100*len(errors)/len(rows):.1f}%)"
          f"   Total cost: ${total_cost:.4f}")
    if unpriced:
        print(f"UNPRICED models (cost excluded from total, add to telemetry_prices.json): "
              f"{', '.join(unpriced)}")

    def group_by(key):
        buckets = {}
        for r in rows:
            buckets.setdefault(r[key], []).append(r)
        return buckets

    print("\n-- By model --")
    for model, rs in sorted(group_by("model").items(), key=lambda kv: -len(kv[1])):
        cost = sum(r["cost_usd"] for r in rs if r["cost_usd"] is not None)
        tin = sum(r["tokens_in"] or 0 for r in rs)
        tout = sum(r["tokens_out"] or 0 for r in rs)
        print(f"  {model:35s} calls={len(rs):5d}  cost=${cost:8.4f}  "
              f"tokens_in={tin:8d}  tokens_out={tout:8d}")

    print("\n-- By route --")
    for route, rs in sorted(group_by("route").items(), key=lambda kv: -len(kv[1])):
        cost = sum(r["cost_usd"] for r in rs if r["cost_usd"] is not None)
        lat = sorted(r["latency_ms"] for r in rs)
        errs = sum(1 for r in rs if not r["ok"])
        p50, p95 = _pct(lat, 0.50), _pct(lat, 0.95)
        print(f"  {route:20s} calls={len(rs):5d}  cost=${cost:8.4f}  "
              f"errors={errs:3d}  p50={p50:7.0f}ms  p95={p95:7.0f}ms")

    print("\n-- By day --")
    days = {}
    for r in rows:
        day = time.strftime("%Y-%m-%d", time.localtime(r["ts"]))
        days.setdefault(day, []).append(r)
    for day, rs in sorted(days.items()):
        cost = sum(r["cost_usd"] for r in rs if r["cost_usd"] is not None)
        errs = sum(1 for r in rs if not r["ok"])
        print(f"  {day}  calls={len(rs):5d}  cost=${cost:8.4f}  errors={errs:3d}")

    if errors:
        print("\n-- Recent errors --")
        for r in errors[-10:]:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"]))
            print(f"  {ts}  {r['route']:20s} {r['model']:25s} {r['error']}")


if __name__ == "__main__":
    sys.exit(main())
