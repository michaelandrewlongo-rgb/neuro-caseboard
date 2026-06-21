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


def test_woven_flags_defaults(monkeypatch):
    for k in ("LITERATURE_WEAVE", "LITERATURE_RECENCY_BOOST",
              "LITERATURE_PRECISION_GATE", "LITERATURE_PRECISION_MIN_OVERLAP"):
        monkeypatch.delenv(k, raising=False)
    from neuro_caseboard.literature.config import load_literature_config
    cfg = load_literature_config()
    assert cfg.weave is False
    assert cfg.recency_boost == 0
    assert cfg.precision_gate is True
    assert cfg.precision_min_overlap == 1


def test_woven_flags_env_overrides(monkeypatch):
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    monkeypatch.setenv("LITERATURE_RECENCY_BOOST", "2")
    monkeypatch.setenv("LITERATURE_PRECISION_GATE", "off")
    monkeypatch.setenv("LITERATURE_PRECISION_MIN_OVERLAP", "3")
    from neuro_caseboard.literature.config import load_literature_config
    cfg = load_literature_config()
    assert cfg.weave is True
    assert cfg.recency_boost == 2
    assert cfg.precision_gate is False
    assert cfg.precision_min_overlap == 3
