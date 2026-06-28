#!/usr/bin/env python3
"""Row counts + order-independent id-hash per LanceDB table (read-only index provenance)."""
from __future__ import annotations

import hashlib
import json
import os
import sys


def fingerprint_ids(rows: int, ids: list[str], schema: list[str]) -> dict:
    h = hashlib.sha256("\n".join(sorted(map(str, ids))).encode("utf-8")).hexdigest()
    return {"rows": rows, "schema": sorted(schema), "id_sha256": h}


def fingerprint_index(index_dir: str, tables=("chunks", "figures", "cards")) -> dict:
    import lancedb

    db = lancedb.connect(index_dir)
    out: dict = {}
    for name in tables:
        t = db.open_table(name)
        df = t.to_pandas()
        idcol = "id" if "id" in df.columns else df.columns[0]
        out[name] = fingerprint_ids(
            int(t.count_rows()),
            df[idcol].astype(str).tolist(),
            [f.name for f in t.schema],
        )
    return out


if __name__ == "__main__":
    idx = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "INDEX_DIR", "/home/michael/neuro-textbook-rag/index")
    print(json.dumps({"index_dir": idx, "tables": fingerprint_index(idx)}, indent=2))
