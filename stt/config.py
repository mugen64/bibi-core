import tomllib
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).parent


@dataclass
class ModelsConfig:
    directory: str = "./models"
    default: str = "ggml-base"

    def __post_init__(self):
        if self.directory.startswith("./"):
            self.directory = BASE_DIR / self.directory
        else:
            self.directory = Path(self.directory)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5001
    grpc_port: int = 50051  # matches gateway.toml's stt_addr


@dataclass
class Config:
    models: ModelsConfig
    server: ServerConfig

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> "Config":
        path = Path(path)
        data = tomllib.loads(path.read_text()) if path.exists() else {}

        return cls(
            models=ModelsConfig(**data.get("models", {})),
            server=ServerConfig(**data.get("server", {})),
        )


config = Config.load()
