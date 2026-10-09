from config import Config


def test_defaults_when_file_is_missing(tmp_path):
    cfg = Config.load(tmp_path / "does-not-exist.toml")
    assert cfg.models.default == "ggml-base"
    assert cfg.engine.provider == "whispercpp"
    assert cfg.server.log_level == "INFO"


def test_overrides_from_toml(tmp_path):
    toml_path = tmp_path / "config.toml"
    toml_path.write_text(
        """
        [models]
        default = "custom-model"
        max_loaded = 7

        [engine]
        provider = "mock"

        [server]
        log_level = "debug"
        """
    )
    cfg = Config.load(toml_path)
    assert cfg.models.default == "custom-model"
    assert cfg.models.max_loaded == 7
    assert cfg.engine.provider == "mock"
    # casing normalizes to uppercase so logging.basicConfig() doesn't choke
    assert cfg.server.log_level == "DEBUG"
