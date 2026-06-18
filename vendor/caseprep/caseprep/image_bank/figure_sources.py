"""Adapters that turn each corpus into FigureRecords for the figure store."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]


def _parse_tagfield(value: Any) -> list[str]:
    if not value:
        return []
    text = str(value)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [part for part in text.split(",")]


def normalize_tags(*fields: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for f in fields:
        for raw in _parse_tagfield(f):
            t = raw.strip().lower()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def image_bank_records(conn: sqlite3.Connection, *, embed_fn: EmbedFn,
                       batch: int = 256) -> Iterator[FigureRecord]:
    cur = conn.execute(
        "SELECT i.fig_id, i.pmcid, i.pmid, i.local_path, i.caption, "
        "l.anatomy, l.pathology, l.procedure, l.keywords, l.caption_summary "
        "FROM images i JOIN labels l ON i.fig_id = l.fig_id "
        "WHERE l.is_neurosurgical = 1"
    )
    pending: list[tuple[FigureRecord, str]] = []

    def flush() -> Iterator[FigureRecord]:
        if not pending:
            return
        vecs = embed_fn([txt for _, txt in pending])
        for (rec, _), v in zip(pending, vecs):
            rec.embedding = list(v)
            yield rec
        pending.clear()

    for fig_id, pmcid, pmid, local_path, caption, anatomy, pathology, procedure, keywords, csum in cur:
        if not local_path or not Path(local_path).exists():
            continue
        tags = normalize_tags(keywords, anatomy, pathology, procedure)
        cap = str(csum or caption or "")
        rec = FigureRecord(
            source="image_bank", fig_id=str(fig_id), tags=tags, caption=cap,
            image_path=str(local_path), image_blob=None,
            source_ref={"pmcid": str(pmcid or ""), "pmid": str(pmid or "")},
            embedding=[],
        )
        pending.append((rec, cap or " "))
        if len(pending) >= batch:
            yield from flush()
    yield from flush()


def textbook_records(rows: Iterable[dict[str, Any]]) -> Iterator[FigureRecord]:
    for row in rows:
        emb = row.get("embedding")
        img = row.get("image_data")
        if not emb or not img:
            continue
        tags = normalize_tags(row.get("vlm_keywords"), row.get("vlm_anatomy"),
                              row.get("vlm_pathology"), row.get("vlm_procedure"))
        cap = str(row.get("caption_vlm") or row.get("caption") or "")
        yield FigureRecord(
            source="textbook", fig_id=str(row.get("id")), tags=tags, caption=cap,
            image_path="", image_blob=bytes(img),
            source_ref={"heading_path": str(row.get("heading_path") or "")},
            embedding=[float(x) for x in emb],
        )
