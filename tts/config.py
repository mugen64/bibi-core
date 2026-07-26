from pathlib import Path
import tomllib


BASE_DIR = Path(__file__).parent


def load_config():
    config_path = BASE_DIR / "config.toml"

    with open(config_path, "rb") as file:
        return tomllib.load(file)


config = load_config()


# Voice configuration
voice_directory = config["voices"]["directory"]
if voice_directory.startswith("./"):
    VOICE_DIR = BASE_DIR / voice_directory
else:
    VOICE_DIR = Path(voice_directory)

DEFAULT_VOICE = config["voices"]["default"]


# Piper configuration
SAMPLE_RATE = config["piper"]["sample_rate"]

