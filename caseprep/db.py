"""SQLite persistence for CasePrep — case plans, papers, and images."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path.cwd() / "caseprep.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS caseplans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    output_dir  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    summary     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid        TEXT NOT NULL,
    title       TEXT DEFAULT '',
    authors     TEXT DEFAULT '',
    source      TEXT DEFAULT '',
    pubdate     TEXT DEFAULT '',
    doi         TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    abstract    TEXT DEFAULT '',
    structured  TEXT DEFAULT '{}',   -- JSON: {BACKGROUND: ..., METHODS: ..., ...}
    fulltext    TEXT DEFAULT '',
    tier        TEXT DEFAULT '',      -- 'pmc', 'structured', 'plain', or ''
    caseplan_id INTEGER NOT NULL REFERENCES caseplans(id) ON DELETE CASCADE,
    search_axis TEXT DEFAULT '',      -- 'outcomes', 'technique', 'complications', 'reviews', 'radiology'
    UNIQUE(pmid, caseplan_id)
);

CREATE TABLE IF NOT EXISTS images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    pmid        TEXT DEFAULT '',
    title       TEXT DEFAULT '',
    caption     TEXT DEFAULT '',
    journal     TEXT DEFAULT '',
    authors     TEXT DEFAULT '',
    pubdate     TEXT DEFAULT '',
    img_large   TEXT DEFAULT '',
    local_path  TEXT DEFAULT '',
    caseplan_id INTEGER NOT NULL REFERENCES caseplans(id) ON DELETE CASCADE,
    UNIQUE(uid, caseplan_id)
);

CREATE TABLE IF NOT EXISTS search_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT NOT NULL,
    tool        TEXT NOT NULL,         -- 'search_pubmed', 'search_radiology', 'build_caseplan'
    results_count INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class CasePrepDB:
    """Thin SQLite wrapper for CasePrep persistence."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── Case plans ──────────────────────────────────────────────────────────

    def save_caseplan(
        self,
        topic: str,
        slug: str,
        output_dir: str,
        summary: str = "",
    ) -> int:
        """Insert a new case plan. Returns the row id."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO caseplans (topic, slug, output_dir, summary) VALUES (?, ?, ?, ?)",
            (topic, slug, str(output_dir), summary),
        )
        if cur.lastrowid == 0:
            # Already exists — get the existing id
            row = self.conn.execute(
                "SELECT id FROM caseplans WHERE slug = ?", (slug,)
            ).fetchone()
            return row["id"]
        return cur.lastrowid

    def get_caseplan(self, slug: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM caseplans WHERE slug = ?", (slug,)
        ).fetchone()
        return dict(row) if row else None

    def list_caseplans(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM caseplans ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Papers ──────────────────────────────────────────────────────────────

    def save_paper(
        self,
        pmid: str,
        caseplan_id: int,
        *,
        title: str = "",
        authors: str = "",
        source: str = "",
        pubdate: str = "",
        doi: str = "",
        url: str = "",
        abstract: str = "",
        structured: dict | None = None,
        fulltext: str = "",
        tier: str = "",
        search_axis: str = "",
    ) -> int:
        struct_json = json.dumps(structured or {})
        cur = self.conn.execute(
            """INSERT OR REPLACE INTO papers
               (pmid, title, authors, source, pubdate, doi, url,
                abstract, structured, fulltext, tier, caseplan_id, search_axis)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pmid, title, authors, source, pubdate, doi, url,
             abstract, struct_json, fulltext, tier, caseplan_id, search_axis),
        )
        return cur.lastrowid

    def get_papers(self, caseplan_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE caseplan_id = ? ORDER BY id", (caseplan_id,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["structured"] = json.loads(d.get("structured") or "{}")
            results.append(d)
        return results

    # ── Images ──────────────────────────────────────────────────────────────

    def save_image(
        self,
        uid: str,
        caseplan_id: int,
        *,
        pmid: str = "",
        title: str = "",
        caption: str = "",
        journal: str = "",
        authors: str = "",
        pubdate: str = "",
        img_large: str = "",
        local_path: str = "",
    ) -> int:
        cur = self.conn.execute(
            """INSERT OR REPLACE INTO images
               (uid, pmid, title, caption, journal, authors, pubdate,
                img_large, local_path, caseplan_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, pmid, title, caption, journal, authors, pubdate,
             img_large, local_path, caseplan_id),
        )
        return cur.lastrowid

    def get_images(self, caseplan_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM images WHERE caseplan_id = ? ORDER BY id", (caseplan_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Search history ──────────────────────────────────────────────────────

    def log_search(self, query: str, tool: str, results_count: int = 0) -> int:
        cur = self.conn.execute(
            "INSERT INTO search_history (query, tool, results_count) VALUES (?, ?, ?)",
            (query, tool, results_count),
        )
        return cur.lastrowid

    def get_search_history(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM search_history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
