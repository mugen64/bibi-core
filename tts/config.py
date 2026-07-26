from pathlib import Path
import tomllib


BASE_DIR = Path(__file__).parent


def load_config():
    config_path = BASE_DIR / "config.toml"

    with open(config_path, "rb") as file:
        return tomllib.load(file)


config = load_config()


# Voice configuration
VOICE_DIR = BASE_DIR / config["voices"]["directory"]
DEFAULT_VOICE = config["voices"]["default"]


# Piper configuration
SAMPLE_RATE = config["piper"]["sample_rate"]

