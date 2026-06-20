#!/usr/bin/env python3
"""
Wrapper to run the Image Bank labeler with proper clean env vars.
"""
import os
import sys

# ── Find and load env vars cleanly ──────────────────────────────────────────
def load_dotenv(path):
    """Load env vars from a .env file, stripping Windows \\r."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\r").strip('"').strip("'")
                    os.environ[k] = v  # override to avoid \\r contamination
    except OSError:
        pass

load_dotenv("/mnt/c/Users/Michael/Desktop/PAPERS/.env")
load_dotenv(os.path.expanduser("~/.hermes/.env"))

or_key = os.environ.get("OPENROUTER_API_KEY", "")
if not or_key:
    print("ERROR: OPENROUTER_API_KEY not found", flush=True)
    sys.exit(1)

ncbi_key = os.environ.get("NCBI_API_KEY") or os.environ.get("NCBI_API_KEY_2", "")
print(f"OPENROUTER_API_KEY: {'✓' if or_key else '✗'}", flush=True)
print(f"NCBI_API_KEY: {'✓' if ncbi_key else '✗'}", flush=True)

# ── Run the labeler ─────────────────────────────────────────────────────────
from caseprep.image_bank.labeler import run_labeler, print_summary, init_labels_table, count_unlabeled, count_labeled
from caseprep.image_bank.labeler import DB_PATH, LABEL_MODEL
import sqlite3
import asyncio
import time

conn = sqlite3.connect(str(DB_PATH))
conn.execute("PRAGMA journal_mode=WAL")
init_labels_table(conn)

unlabeled = count_unlabeled(conn)
labeled = count_labeled(conn)
print(f"\n{'='*60}", flush=True)
print(f"  Image Bank Labeler — Starting", flush=True)
print(f"  Model: {LABEL_MODEL}", flush=True)
print(f"  Already labeled: {labeled}", flush=True)
print(f"  To label: {unlabeled}", flush=True)
print(f"{'='*60}\n", flush=True)

start = time.time()
asyncio.run(run_labeler(conn))
elapsed = time.time() - start

print_summary(conn)
print(f"\n  Elapsed: {elapsed/60:.1f} min", flush=True)
conn.close()
