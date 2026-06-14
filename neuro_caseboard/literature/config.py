from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class LiteratureConfig:
    enabled: bool
    recency_years: int
    k: int
    cache_ttl_days: int
    ncbi_api_key: str
    cache_dir: str


def load_literature_config() -> LiteratureConfig:
    default_cache = str(Path.home() / ".cache" / "neuro_caseboard" / "pubmed")
    return LiteratureConfig(
        enabled=_flag(os.environ.get("LITERATURE_RETRIEVAL", "true")),
        recency_years=int(os.environ.get("LITERATURE_RECENCY_YEARS", "7")),
        k=int(os.environ.get("LITERATURE_K", "8")),
        cache_ttl_days=int(os.environ.get("LITERATURE_CACHE_TTL_DAYS", "14")),
        ncbi_api_key=(os.environ.get("NCBI_API_KEY")
                      or os.environ.get("NCBI_API_KEY_2") or "").strip(),
        cache_dir=os.environ.get("LITERATURE_CACHE_DIR", default_cache),
    )
