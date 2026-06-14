from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from .retriever import LiteratureRecord


class LiteratureCache:
    """On-disk TTL cache of retrieved records (the rate-limited network step)."""

    def __init__(self, cache_dir: str, *, ttl_days: int = 14, now=time.time):
        self._dir = Path(cache_dir)
        self._ttl = ttl_days * 86400
        self._now = now

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> list[LiteratureRecord] | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            blob = json.loads(p.read_text())
        except Exception:
            return None
        if self._now() - blob.get("ts", 0) > self._ttl:
            return None
        try:
            return [LiteratureRecord(**r) for r in blob.get("records", [])]
        except Exception:
            return None

    def set(self, key: str, records: list[LiteratureRecord]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {"ts": self._now(), "records": [asdict(r) for r in records]}
        self._path(key).write_text(json.dumps(payload))
