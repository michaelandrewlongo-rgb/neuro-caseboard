#!/usr/bin/env python3
"""
Textbook Figures — caption embedding pass (all-mpnet-base-v2, 768-d).

Populates ``textbook_figures.embedding`` (vector(768)) so figures are
retrievable by cosine similarity in the same 768-d space as
``text_passages``.  Run AFTER ``textbook_labeler`` so the VLM captions exist.

Embed text per row = best available:
    caption_vlm  ->  caption  ->  heading_path
optionally enriched with vlm_keywords for recall.

Idempotent: only embeds rows ``WHERE embedding IS NULL``.

Usage:
    python -m caseprep.image_bank.textbook_embed
    python -m caseprep.image_bank.textbook_embed --limit 200
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

MODEL_NAME = "all-mpnet-base-v2"  # 768-d, matches text_passages dim
BATCH = 256

_DB_URL_ENV = "PAPERS_CORPUS_DB_URL"
_DEFAULT_DB_URL = (
    "postgresql+psycopg://corpus_pipeline:corpus_pipeline@127.0.0.1:5432/corpus_pipeline"
)


def _db_kwargs() -> dict[str, Any]:
    url = os.environ.get(_DB_URL_ENV, _DEFAULT_DB_URL)
    m = re.match(r"postgresql(?:\+psycopg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise ValueError(f"Unsupported DB URL: {url[:60]}")
    user, pwd, host, port, db = m.groups()
    return {"host": host, "port": int(port), "dbname": db, "user": user, "password": pwd}


def _connect():
    import psycopg2
    from pgvector.psycopg2 import register_vector

    conn = psycopg2.connect(**_db_kwargs())
    register_vector(conn)
    conn.commit()  # clear the txn register_vector opened by its OID lookup
    return conn


def _embed_text(row: dict) -> str:
    base = (row.get("caption_vlm") or row.get("caption") or row.get("heading_path") or "").strip()
    kws = row.get("vlm_keywords")
    if kws:
        try:
            terms = json.loads(kws)
            if terms:
                base = f"{base}  Keywords: {', '.join(terms)}"
        except (json.JSONDecodeError, TypeError):
            pass
    return base or "(no caption)"


def fetch_batch(conn, size: int):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, caption_vlm, caption, heading_path, vlm_keywords
        FROM textbook_figures
        WHERE embedding IS NULL
        ORDER BY id
        LIMIT %s
        """,
        (size,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def count_remaining(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM textbook_figures WHERE embedding IS NULL")
    return cur.fetchone()[0]


def main(limit):
    import numpy as np
    from sentence_transformers import SentenceTransformer

    conn = _connect()
    remaining = count_remaining(conn)
    target = remaining if limit is None else min(limit, remaining)
    print(f"  Embedding {target} figure captions via {MODEL_NAME} (768-d)...")

    device = "cuda" if os.environ.get("FORCE_CPU") != "1" else "cpu"
    try:
        model = SentenceTransformer(MODEL_NAME, device=device)
    except Exception as exc:
        print(f"  [WARN] {device} init failed ({exc}); falling back to CPU")
        model = SentenceTransformer(MODEL_NAME, device="cpu")

    done = 0
    while done < target:
        rows = fetch_batch(conn, min(BATCH, target - done))
        if not rows:
            break
        texts = [_embed_text(r) for r in rows]
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=64).astype(np.float32)
        cur = conn.cursor()
        for r, v in zip(rows, vecs):
            cur.execute("UPDATE textbook_figures SET embedding = %s WHERE id = %s", (v, r["id"]))
        conn.commit()
        done += len(rows)
        print(f"    {done}/{target} embedded", flush=True)

    conn.close()
    print(f"  Done: {done} embedded")


if __name__ == "__main__":
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    main(limit)
