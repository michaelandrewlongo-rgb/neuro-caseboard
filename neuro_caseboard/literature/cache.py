from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from .retriever import LiteratureRecord


# An EMPTY result is cached too (to avoid hammering NCBI for a query that genuinely matches
# nothing), but it must not outlive a transient cause. A failed LLM query-rewrite or an NCBI
# hiccup yields [], and at the full 14-day TTL that empty answer kept the literature lane
# silently blank for weeks after the outage ended. Short TTL: still shields NCBI, self-heals.
# ponytail: one hour, no config knob until something actually needs a different value.
EMPTY_TTL_SECONDS = 3600


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
        raw = blob.get("records", [])
        ttl = self._ttl if raw else min(self._ttl, EMPTY_TTL_SECONDS)
        if self._now() - blob.get("ts", 0) > ttl:
            return None
        try:
            return [LiteratureRecord(**r) for r in raw]
        except Exception:
            return None

    def set(self, key: str, records: list[LiteratureRecord]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {"ts": self._now(), "records": [asdict(r) for r in records]}
        self._path(key).write_text(json.dumps(payload))
