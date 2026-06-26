from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    """Populate os.environ from a project .env, without depending on python-dotenv.

    Looks for a .env at the repo root (anchored to this file) first, then the current
    working directory and its parents; the first file found wins. Existing environment
    variables are never overwritten — real env always beats the file, matching
    python-dotenv's default (override=False). This lets a local, gitignored .env supply
    secrets like NCBI_API_KEY to every engine entrypoint (API, CLI, Streamlit) with no
    extra setup in future sessions.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    if _flag(os.environ.get("NEURO_CASEBOARD_SKIP_DOTENV", "")):
        return  # tests/CI opt out so an ambient developer .env can't leak into a controlled env
    _DOTENV_LOADED = True
    repo_root = Path(__file__).resolve().parents[2]  # neuro_caseboard/literature/config.py -> repo
    cwd = Path.cwd()
    candidates = [repo_root / ".env", *(p / ".env" for p in (cwd, *cwd.parents))]
    seen: set[Path] = set()
    for env_path in candidates:
        if env_path in seen:
            continue
        seen.add(env_path)
        try:
            text = env_path.read_text(encoding="utf-8-sig")  # utf-8-sig drops a leading BOM
        except (OSError, UnicodeDecodeError):
            continue  # unreadable or non-UTF-8 .env must never crash an entrypoint
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            value = value.strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]  # strip matching surrounding quotes; keep any inner '#'
            else:
                hash_idx = value.find(" #")
                if hash_idx != -1:
                    value = value[:hash_idx].rstrip()  # drop an unquoted inline comment
            if key and key not in os.environ:
                os.environ[key] = value
        return  # first .env found wins


@dataclass(frozen=True)
class LiteratureConfig:
    enabled: bool
    recency_years: int
    k: int
    cache_ttl_days: int
    ncbi_api_key: str
    cache_dir: str
    weave: bool = True
    recency_boost: int = 0
    precision_gate: bool = True
    precision_min_overlap: int = 1


def load_literature_config() -> LiteratureConfig:
    _load_dotenv_once()
    default_cache = str(Path.home() / ".cache" / "neuro_caseboard" / "pubmed")
    return LiteratureConfig(
        enabled=_flag(os.environ.get("LITERATURE_RETRIEVAL", "true")),
        recency_years=int(os.environ.get("LITERATURE_RECENCY_YEARS", "7")),
        k=int(os.environ.get("LITERATURE_K", "12")),
        cache_ttl_days=int(os.environ.get("LITERATURE_CACHE_TTL_DAYS", "14")),
        ncbi_api_key=(os.environ.get("NCBI_API_KEY")
                      or os.environ.get("NCBI_API_KEY_2") or "").strip(),
        cache_dir=os.environ.get("LITERATURE_CACHE_DIR", default_cache),
        weave=_flag(os.environ.get("LITERATURE_WEAVE", "true")),
        recency_boost=int(os.environ.get("LITERATURE_RECENCY_BOOST", "0")),
        precision_gate=_flag(os.environ.get("LITERATURE_PRECISION_GATE", "true")),
        precision_min_overlap=int(os.environ.get("LITERATURE_PRECISION_MIN_OVERLAP", "1")),
    )
