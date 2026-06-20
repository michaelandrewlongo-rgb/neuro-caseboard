from __future__ import annotations

import hashlib
import re


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def fingerprint(kind: str, locus: str, signature: str) -> str:
    raw = f"{_norm(kind)}|{_norm(locus)}|{_norm(signature)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
