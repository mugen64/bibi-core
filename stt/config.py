import tomllib
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).parent


@dataclass
class ModelsConfig:
    directory: str = "./models"
    default: str = "ggml-base"
    max_loaded: int = 4

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
    log_level: str = "INFO"

    def __post_init__(self):
        # logging.basicConfig() requires an uppercase level name
        # ("INFO", not "info") - normalize so either casing works in
        # config.toml.
        self.log_level = self.log_level.upper()


@dataclass
class EngineConfig:
    provider: str = "whispercpp"


@dataclass
class Config:
    models: ModelsConfig
    server: ServerConfig
    engine: EngineConfig

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> Config:
        path = Path(path)
        data = tomllib.loads(path.read_text()) if path.exists() else {}

        return cls(
            models=ModelsConfig(**data.get("models", {})),
            server=ServerConfig(**data.get("server", {})),
            engine=EngineConfig(**data.get("engine", {})),
        )


config = Config.load()
