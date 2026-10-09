from config import Config


def test_defaults_when_file_is_missing(tmp_path):
    cfg = Config.load(tmp_path / "does-not-exist.toml")
    assert cfg.ollama.model == "llama3.1"
    assert cfg.engine.provider == "ollama"
    assert cfg.server.log_level == "INFO"


def test_overrides_from_toml(tmp_path):
    toml_path = tmp_path / "config.toml"
    toml_path.write_text(
        """
        [ollama]
        model = "custom-model"

        [engine]
        provider = "mock"

        [server]
        log_level = "debug"
        """
    )
    cfg = Config.load(toml_path)
    assert cfg.ollama.model == "custom-model"
    assert cfg.engine.provider == "mock"
    # casing normalizes to uppercase so logging.basicConfig() doesn't choke
    assert cfg.server.log_level == "DEBUG"
