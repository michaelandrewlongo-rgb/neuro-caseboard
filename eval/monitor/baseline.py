from __future__ import annotations

import json
from pathlib import Path


def load_baseline(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def is_regression(before: float | None, after: float, *, rel_margin: float,
                  abs_floor: float) -> bool:
    if after < abs_floor:
        return True
    if before is not None and after < before - rel_margin:
        return True
    return False
