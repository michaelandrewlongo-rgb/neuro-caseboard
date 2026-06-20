import importlib
from neuro_caseboard.literature.config import load_literature_config


def test_defaults_when_env_empty(monkeypatch):
    for k in ("LITERATURE_RETRIEVAL", "LITERATURE_RECENCY_YEARS", "LITERATURE_K",
              "LITERATURE_CACHE_TTL_DAYS", "NCBI_API_KEY", "NCBI_API_KEY_2"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_literature_config()
    assert cfg.enabled is True
    assert cfg.recency_years == 7
    assert cfg.k == 12
    assert cfg.cache_ttl_days == 14
    assert cfg.ncbi_api_key == ""


def test_reads_env_and_key_fallback(monkeypatch):
    monkeypatch.setenv("LITERATURE_RETRIEVAL", "false")
    monkeypatch.setenv("LITERATURE_K", "5")
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    monkeypatch.setenv("NCBI_API_KEY_2", "fallback-key")
    cfg = load_literature_config()
    assert cfg.enabled is False
    assert cfg.k == 5
    assert cfg.ncbi_api_key == "fallback-key"
