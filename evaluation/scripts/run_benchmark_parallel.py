#!/usr/bin/env python3
"""Guarded, bounded-parallel wrapper around ``run_benchmark.py`` for 67-Q A/B runs.

Why this exists (all numbers measured on the 16 GB WSL2 box, see the design spec):
- Per-worker peak RSS is ~5 GB and memory — not CPU — is the bottleneck. ``N × 5 GB + ~2 GB OS``
  must stay under 16 GB with swap untouched, so concurrency is capped at **2** (N=3 ⇒ swap thrash).
- ``run.jsonl`` records are 90–140 KB (≫ 4 KB PIPE_BUF), so two processes appending to one file
  would corrupt it. Each worker therefore writes its **own** shard ``run.jsonl``; we merge at the end.

The runner itself is unchanged: each shard is driven by the same one-id-per-call ``--resume`` loop,
so every question is a short-lived process that exits and releases its ~5 GB (flat memory ceiling,
never accumulating — unlike a long-lived pool).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ── calibration knobs (the physical box needs tuning a minimal model can't see) ──────────────
PEAK_GB = 5.5      # 5.07 GB observed VmHWM + margin for heavier (longer-context) questions
CUSHION_GB = 2.0   # buff/cache reclaim lag + transient spikes; keep swap untouched
N_MAX = 2          # research finding: 3×5 GB + OS > 16 GB ⇒ swap. Do not raise without re-measuring.

RUNNER = Path(__file__).parent / "run_benchmark.py"


# ── pure functions (unit-tested; no psutil/subprocess/Vertex) ────────────────────────────────
def choose_n(available_gb: float, *, peak_gb: float = PEAK_GB,
             cushion_gb: float = CUSHION_GB, n_max: int = N_MAX) -> int:
    """Workers that fit in RAM without swapping. 0 ⇒ not even one fits safely (caller aborts)."""
    raw = math.floor((available_gb - cushion_gb) / peak_gb)
    return max(0, min(raw, n_max))


def round_robin_split(ids: list, n: int) -> list:
    """Deal ids across n shards round-robin. Returns exactly n lists (some may be empty)."""
    return [ids[i::n] for i in range(n)]


def merge_records(record_lists: list) -> list:
    """Flatten shard records, dedup by question_id (last wins), preserve first-seen order."""
    by_id, order = {}, []
    for recs in record_lists:
        for r in recs:
            qid = r.get("question_id")
            if qid not in by_id:
                order.append(qid)
            by_id[qid] = r
    return [by_id[q] for q in order]


def parse_jsonl_tolerant(text: str) -> list:
    """Parse JSONL, skipping blank or unparseable lines (e.g. a crash-truncated last record)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ── live glue (psutil lazy; falls back to /proc so the gate works headless) ──────────────────
def available_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 2 ** 30
    except Exception:
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2 ** 20  # kB → GiB
        except OSError:
            pass
        return 0.0


def top_processes(k: int = 8) -> list:
    """(rss_gb, pid, name) for the k biggest RSS hogs — shown on abort so the user knows what to close."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                procs.append((p.info["memory_info"].rss / 2 ** 30, p.info["pid"], p.info["name"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
        return sorted(procs, reverse=True)[:k]
    except Exception:
        return []


def _run_shard(shard_dir: Path, ids: list) -> None:
    shard_dir.mkdir(parents=True, exist_ok=True)
    for qid in ids:
        cp = subprocess.run(
            [sys.executable, str(RUNNER), "--run-dir", str(shard_dir),
             "--start-id", qid, "--end-id", qid, "--resume"],
            env=os.environ,
        )
        if cp.returncode != 0:
            print(f"[parallel] WARN shard worker for {qid} exited {cp.returncode} "
                  f"(record may be missing; --resume will retry next run)", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Memory-guarded parallel 67-Q benchmark run.")
    ap.add_argument("--run-dir", required=True, help="Parent run dir; shards land in <run-dir>/shard-<i>.")
    ap.add_argument("--ids", help="Space/comma-separated question ids.")
    ap.add_argument("--ids-file", help="File with one id per line (alternative to --ids).")
    ap.add_argument("--max-workers", type=int, default=N_MAX, help=f"Cap on concurrency (default {N_MAX}).")
    ap.add_argument("--dry-run", action="store_true", help="Print the gate decision and exit.")
    args = ap.parse_args(argv)

    if args.ids_file:
        ids = [ln.strip() for ln in open(args.ids_file) if ln.strip()]
    elif args.ids:
        ids = [t for t in args.ids.replace(",", " ").split() if t]
    else:
        ap.error("one of --ids or --ids-file is required")

    avail = available_gb()
    n = choose_n(avail, n_max=args.max_workers)
    print(f"[parallel] available={avail:.1f} GB  peak/worker≈{PEAK_GB} GB  cushion={CUSHION_GB} GB "
          f"→ N={n} (cap {args.max_workers})")
    if n == 0:
        print(f"[parallel] ABORT: < {PEAK_GB + CUSHION_GB:.1f} GB free — not enough to fit even one "
              f"worker without swapping. Close some of these and retry:", file=sys.stderr)
        for rss, pid, name in top_processes():
            print(f"           {rss:5.2f} GB  pid={pid:<8} {name}", file=sys.stderr)
        return 2

    run_dir = Path(args.run_dir)
    shards = [(i, s) for i, s in enumerate(round_robin_split(ids, n)) if s]
    print(f"[parallel] {len(ids)} question(s) across {len(shards)} shard(s): "
          + ", ".join(f"shard-{i}={len(s)}" for i, s in shards))
    if args.dry_run:
        return 0

    run_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=len(shards)) as ex:
        list(ex.map(lambda t: _run_shard(run_dir / f"shard-{t[0]}", t[1]), shards))

    # merge shard run.jsonls → run_dir/run.jsonl (idempotent; rebuilt from shards each call)
    record_lists = []
    for i, _ in shards:
        rj = run_dir / f"shard-{i}" / "run.jsonl"
        if rj.exists():
            record_lists.append(parse_jsonl_tolerant(rj.read_text(encoding="utf-8")))
    merged = merge_records(record_lists)
    (run_dir / "run.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged), encoding="utf-8")

    cfg = run_dir / f"shard-{shards[0][0]}" / "run-config.json"
    if cfg.exists():
        (run_dir / "run-config.json").write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"[parallel] merged {len(merged)} record(s) → {run_dir}/run.jsonl  "
          f"(now run finalize_run.py / grading / aggregation as usual)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
