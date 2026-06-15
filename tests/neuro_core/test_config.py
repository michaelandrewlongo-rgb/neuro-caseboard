from neuro_core.config import load_config


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


def test_phase2_defaults_present(tmp_path, monkeypatch):
    # No env file, no overrides -> Phase 2 defaults resolve.
    monkeypatch.delenv("SYNTH_PROVIDER", raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.synth_provider == "vertex"
    assert cfg.google_cloud_location == "us-central1"
    assert cfg.vertex_model  # non-empty Pro-tier default
    assert cfg.max_figure_images == 5
    assert cfg.figure_dpi == 160
    assert abs(cfg.figure_area_threshold - 0.1) < 1e-9
    assert str(cfg.assets_dir).endswith("assets/figures")


def test_env_overrides_synth_provider(tmp_path, monkeypatch):
    # Process env beats the file (see precedence test), so clear it to prove the
    # .env file path itself works — a dev shell defaulting to Vertex must not leak in.
    monkeypatch.delenv("SYNTH_PROVIDER", raising=False)
    monkeypatch.delenv("MAX_FIGURE_IMAGES", raising=False)
    env = tmp_path / ".env"
    env.write_text("SYNTH_PROVIDER=openrouter\nMAX_FIGURE_IMAGES=1\n")
    cfg = load_config(env_file=str(env))
    assert cfg.synth_provider == "openrouter"
    assert cfg.max_figure_images == 1


def test_phase2b_visual_defaults(tmp_path):
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.visual_model  # non-empty default
    assert cfg.visual_retrieve_k == 10
    assert cfg.visual_retrieval is True


def test_visual_retrieval_toggle_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("VISUAL_RETRIEVAL=off\nVISUAL_RETRIEVE_K=5\n")
    cfg = load_config(env_file=str(env))
    assert cfg.visual_retrieval is False
    assert cfg.visual_retrieve_k == 5


def test_default_vertex_model_is_pro(monkeypatch):
    monkeypatch.delenv("VERTEX_MODEL", raising=False)
    cfg = load_config(env_file="does-not-exist.env")
    assert cfg.vertex_model == "gemini-2.5-pro"


def test_default_app_passcode_is_empty(monkeypatch):
    monkeypatch.delenv("APP_PASSCODE", raising=False)
    cfg = load_config(env_file="does-not-exist.env")
    assert cfg.app_passcode == ""


def test_local_provider_defaults(tmp_path, monkeypatch):
    for k in ("LOCAL_BASE_URL", "LOCAL_MODEL"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.local_base_url == "http://localhost:11434/v1"
    assert cfg.local_model == "qwen2.5:7b"


def test_gpu_guard_defaults(tmp_path, monkeypatch):
    for k in ("GPU_GUARD", "GPU_MIN_FREE_MIB"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.gpu_guard is True
    assert cfg.gpu_min_free_mib == 10000


def test_gpu_guard_toggle_off(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GPU_GUARD=off\nGPU_MIN_FREE_MIB=8000\n")
    cfg = load_config(env_file=str(env))
    assert cfg.gpu_guard is False
    assert cfg.gpu_min_free_mib == 8000


def test_cards_source_defaults(tmp_path, monkeypatch):
    for k in ("CARDS_SOURCE_DB", "CARDS_SOURCE_TABLE", "CARDS_MEDIA_TABLE",
              "CARDS_MEDIA_DIR"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert str(cfg.cards_source_db).endswith("abns-board-review-lancedb")
    assert cfg.cards_source_table == "cards"
    assert cfg.cards_media_table == "images"
    assert cfg.cards_media_dir == ""


def test_cards_source_env_override(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CARDS_SOURCE_TABLE=notes\nCARDS_MEDIA_TABLE=\n")
    cfg = load_config(env_file=str(env))
    assert cfg.cards_source_table == "notes"
    assert cfg.cards_media_table == ""   # "" disables media resolution
