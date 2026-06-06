import os
from dataclasses import dataclass
from pathlib import Path

DEFAULTS = {
    "CORPUS_DIR": "/mnt/d/textbook_pdfs",
    "INDEX_DIR": str(Path.home() / "neuro-textbook-rag" / "index"),
    "EMBED_MODEL": "BAAI/bge-large-en-v1.5",
    "RERANK_MODEL": "BAAI/bge-reranker-v2-m3",
    "OPENROUTER_MODEL": "anthropic/claude-sonnet-4.6",
    "OPENROUTER_API_KEY": "",
    "CHUNK_MAX_WORDS": "600",
    "CHUNK_OVERLAP_WORDS": "80",
    "RETRIEVE_K": "20",
    "RERANK_K": "6",
    "EMBED_DEVICE": "cuda",
}


def _parse_env_file(path):
    env = {}
    p = Path(path)
    if not p.exists():
        return env
    for line in p.read_text().splitlines():
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'").replace("\r", "")
        env[key.strip()] = val
    return env


@dataclass
class Config:
    corpus_dir: Path
    index_dir: Path
    embed_model: str
    rerank_model: str
    openrouter_model: str
    openrouter_api_key: str
    chunk_max_words: int
    chunk_overlap_words: int
    retrieve_k: int
    rerank_k: int
    embed_device: str


def load_config(env_file=".env"):
    file_env = _parse_env_file(env_file)

    def get(key):
        if os.environ.get(key):
            return os.environ[key].replace("\r", "")
        if key in file_env:
            return file_env[key]
        return DEFAULTS[key]

    return Config(
        corpus_dir=Path(get("CORPUS_DIR")),
        index_dir=Path(get("INDEX_DIR")),
        embed_model=get("EMBED_MODEL"),
        rerank_model=get("RERANK_MODEL"),
        openrouter_model=get("OPENROUTER_MODEL"),
        openrouter_api_key=get("OPENROUTER_API_KEY"),
        chunk_max_words=int(get("CHUNK_MAX_WORDS")),
        chunk_overlap_words=int(get("CHUNK_OVERLAP_WORDS")),
        retrieve_k=int(get("RETRIEVE_K")),
        rerank_k=int(get("RERANK_K")),
        embed_device=get("EMBED_DEVICE"),
    )
