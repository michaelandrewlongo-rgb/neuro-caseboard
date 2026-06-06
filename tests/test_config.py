from engine.config import load_config


def test_env_file_crlf_and_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('OPENROUTER_API_KEY="sk-file"\r\nRETRIEVE_K=11\r\n')
    monkeypatch.delenv("RETRIEVE_K", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-proc")  # process env wins

    cfg = load_config(env_file=str(env))

    assert cfg.openrouter_api_key == "sk-proc"      # process env beats file
    assert cfg.retrieve_k == 11                      # from file
    assert "\r" not in cfg.openrouter_api_key
    assert cfg.embed_model == "BAAI/bge-large-en-v1.5"  # default


def test_missing_env_file_uses_defaults(tmp_path):
    cfg = load_config(env_file=str(tmp_path / "nope.env"))
    assert cfg.retrieve_k == 20
    assert cfg.rerank_k == 6
