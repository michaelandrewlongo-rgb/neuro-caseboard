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
    "EMBED_DEVICE": "auto",
    "SYNTH_PROVIDER": "vertex",
    "GOOGLE_CLOUD_PROJECT": "",
    "GOOGLE_CLOUD_LOCATION": "us-central1",
    "VERTEX_MODEL": "gemini-2.5-flash",
    "MAX_FIGURE_IMAGES": "3",
    "FIGURE_DPI": "160",
    "FIGURE_AREA_THRESHOLD": "0.1",
    "ASSETS_DIR": str(Path.home() / "neuro-textbook-rag" / "assets" / "figures"),
    "VISUAL_MODEL": "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
    "VISUAL_RETRIEVE_K": "10",
    "VISUAL_RETRIEVAL": "true",
}


def resolve_device(device):
    """Resolve 'auto' to 'cuda' when available, else 'cpu'. Pass other values through."""
    if device != "auto":
        return device
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


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
    synth_provider: str
    google_cloud_project: str
    google_cloud_location: str
    vertex_model: str
    max_figure_images: int
    figure_dpi: int
    figure_area_threshold: float
    assets_dir: Path
    visual_model: str
    visual_retrieve_k: int
    visual_retrieval: bool


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
        synth_provider=get("SYNTH_PROVIDER"),
        google_cloud_project=get("GOOGLE_CLOUD_PROJECT"),
        google_cloud_location=get("GOOGLE_CLOUD_LOCATION"),
        vertex_model=get("VERTEX_MODEL"),
        max_figure_images=int(get("MAX_FIGURE_IMAGES")),
        figure_dpi=int(get("FIGURE_DPI")),
        figure_area_threshold=float(get("FIGURE_AREA_THRESHOLD")),
        assets_dir=Path(get("ASSETS_DIR")),
        visual_model=get("VISUAL_MODEL"),
        visual_retrieve_k=int(get("VISUAL_RETRIEVE_K")),
        visual_retrieval=get("VISUAL_RETRIEVAL").strip().lower() in
        ("1", "true", "yes", "on"),
    )
