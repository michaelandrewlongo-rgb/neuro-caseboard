from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from eval.monitor.contracts import Issue


def load_suppressions(path, *, today: datetime.date | None = None) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    today = today or datetime.date.today()
    entries = yaml.safe_load(p.read_text(encoding="utf-8")) or []
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
