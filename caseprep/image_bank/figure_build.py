"""Offline build: merge image_bank + textbook_figures into one local FigureStore."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from caseprep.image_bank.figure_sources import EmbedFn, image_bank_records, textbook_records
from caseprep.image_bank.figure_store import FigureStore

_HERE = Path(__file__).resolve().parent
DEFAULT_BANK_DB = _HERE / "bank.db"
DEFAULT_STORE = _HERE / "figure_store.sqlite"


def build_figure_store(out_path: str | Path, *, bank_conn: sqlite3.Connection,
                       embed_fn: EmbedFn,
                       textbook_rows: Iterable[dict[str, Any]]) -> int:
    def all_records():
        yield from image_bank_records(bank_conn, embed_fn=embed_fn)
        yield from textbook_records(textbook_rows)
    return FigureStore(out_path).write(all_records())


def _pg_kwargs() -> dict:  # pragma: no cover - needs Postgres
    import os, re
    url = os.environ.get(
        "PAPERS_CORPUS_DB_URL",
        "postgresql+psycopg://corpus_pipeline:corpus_pipeline@127.0.0.1:5432/corpus_pipeline",
    )
    m = re.match(r"postgresql(?:\+psycopg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise ValueError(f"Unsupported DB URL: {url[:60]}")
    user, pwd, host, port, db = m.groups()
    return {"host": host, "port": int(port), "dbname": db, "user": user, "password": pwd}


def _fetch_textbook_rows() -> Iterable[dict[str, Any]]:  # pragma: no cover - needs Postgres
    import psycopg2
    from pgvector.psycopg2 import register_vector
    conn = psycopg2.connect(**_pg_kwargs())
    register_vector(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, caption_vlm, caption, heading_path, vlm_keywords, vlm_anatomy, "
        "vlm_pathology, vlm_procedure, embedding, image_data FROM textbook_figures "
        "WHERE embedding IS NOT NULL AND image_data IS NOT NULL"
    )
    cols = [d[0] for d in cur.description]
    for row in cur:
        d = dict(zip(cols, row))
        d["embedding"] = list(d["embedding"]) if d["embedding"] is not None else None
        yield d


def main() -> None:  # pragma: no cover - real build needs model + Postgres
    from caseprep.image_bank.figure_embed import embed_texts
    n = build_figure_store(
        DEFAULT_STORE, bank_conn=sqlite3.connect(DEFAULT_BANK_DB),
        embed_fn=embed_texts, textbook_rows=_fetch_textbook_rows(),
    )
    print(f"figure_store written: {n} figures -> {DEFAULT_STORE}")


if __name__ == "__main__":  # pragma: no cover
    main()
