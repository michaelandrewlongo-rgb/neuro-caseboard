from __future__ import annotations

import datetime
import json
from pathlib import Path

from eval.monitor.contracts import Issue


def load_suppressions(path, *, today: datetime.date | None = None) -> set[str]:
    """Active suppressed fingerprints from a JSON file (a list of
    ``{"fingerprint", "reason", "expires"?}``). Missing file -> empty set.
    Entries whose ``expires`` date is before ``today`` are dropped.

    JSON (stdlib) is used deliberately so the monitor adds no third-party
    dependency; the file is small and hand-editable.
    """
    p = Path(path)
    if not p.exists():
        return set()
    today = today or datetime.date.today()
    entries = json.loads(p.read_text(encoding="utf-8")) or []
    active: set[str] = set()
    for entry in entries:
        fp = entry.get("fingerprint")
        if not fp:
            continue
        expires = entry.get("expires")
        if expires and datetime.date.fromisoformat(str(expires)) < today:
            continue
        active.add(fp)
    return active


def filter_suppressed(issues: list[Issue], suppressed: set[str]) -> list[Issue]:
    return [i for i in issues if i.fingerprint not in suppressed]
