import tomllib
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).parent


@dataclass
class VoicesConfig:
    directory: Path = Path("./voices")
    default: str = "en_US-lessac-high.onnx"
    max_loaded: int = 3

    def __post_init__(self):
        directory = str(self.directory)
        if directory.startswith("./"):
            self.directory = BASE_DIR / directory
        else:
            self.directory = Path(directory)


@dataclass
class PiperConfig:
    sample_rate: int = 22050


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5000
    grpc_port: int = 50050  # matches gateway.toml's tts_addr


@dataclass
class Config:
    voices: VoicesConfig
    piper: PiperConfig
    server: ServerConfig

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> "Config":
        path = Path(path)
        data = tomllib.loads(path.read_text()) if path.exists() else {}

        return cls(
            voices=VoicesConfig(**data.get("voices", {})),
            piper=PiperConfig(**data.get("piper", {})),
            server=ServerConfig(**data.get("server", {})),
        )


config = Config.load()
