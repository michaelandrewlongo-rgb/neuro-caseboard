"""Local, offline figure store: one SQLite file holding merged figure records
from image_bank + textbook_figures, each with tags, caption, image, citation,
and a unit-norm 768-d embedding (stored as float32 bytes). No numpy."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class FigureRecord:
    source: str                      # "image_bank" | "textbook"
    fig_id: str
    tags: list[str]
    caption: str
    image_path: str                  # local file (image_bank); "" for textbook
    image_blob: bytes | None         # bytes (textbook); None for image_bank
    source_ref: dict[str, Any]       # {"pmcid","pmid"} or {"heading_path"}
    embedding: list[float] = field(default_factory=list)


def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


class FigureStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @staticmethod
    def key(rec: FigureRecord) -> str:
        return f"{rec.source}:{rec.fig_id}"

    def write(self, records: Iterable[FigureRecord]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".sqlite")
        os.close(fd)
        n = 0
        try:
            conn = sqlite3.connect(tmp)
            conn.execute(
                "CREATE TABLE figures (source TEXT, fig_id TEXT, tags TEXT, "
                "caption TEXT, image_path TEXT, image_blob BLOB, source_ref TEXT, "
                "embedding BLOB, PRIMARY KEY (source, fig_id))"
            )
            for r in records:
                conn.execute(
                    "INSERT OR REPLACE INTO figures VALUES (?,?,?,?,?,?,?,?)",
                    (r.source, r.fig_id, json.dumps(r.tags), r.caption,
                     r.image_path, r.image_blob, json.dumps(r.source_ref),
                     _pack(r.embedding)),
                )
                n += 1
            conn.commit()
            conn.close()
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return n

    def load(self) -> list[FigureRecord]:
        if not self.path.exists():
            return []
        conn = sqlite3.connect(self.path)
        rows = conn.execute(
            "SELECT source, fig_id, tags, caption, image_path, image_blob, "
            "source_ref, embedding FROM figures"
        ).fetchall()
        conn.close()
        out: list[FigureRecord] = []
        for src, fid, tags, cap, ipath, iblob, sref, emb in rows:
            out.append(FigureRecord(
                source=src, fig_id=fid, tags=json.loads(tags), caption=cap,
                image_path=ipath or "", image_blob=iblob,
                source_ref=json.loads(sref), embedding=_unpack(emb),
            ))
        return out
