import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OllamaConfig:
    host: str = "http://localhost:11434"
    model: str = "llama3.1"
    temperature: float = 0.7
    context_window: int = 4096
    keep_alive: str = "5m"  # how long Ollama keeps the model loaded
    # How long a successful "model is available" pre-flight check stays
    # valid before we re-check with Ollama. Avoids a round-trip to
    # Ollama on every single /chat request.
    availability_cache_seconds: float = 10.0


@dataclass
class EngineConfig:
    provider: str = "ollama"


@dataclass
class ChunkingConfig:
    # Sentence-boundary chars that trigger a chunk to be sent to TTS
    boundary_chars: list[str] = field(default_factory=lambda: [".", "?", "!"])
    # Fallback: force a chunk even without a boundary char after this many
    # characters, so a long clause without punctuation doesn't stall TTS
    max_chunk_chars: int = 200
    # Minimum chars before we'll even consider chunking - avoids sending
    # a lone "Mr." or "3." as if it were a full sentence
    min_chunk_chars: int = 10


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5002
    grpc_port: int = 50053  # matches gateway.toml's llm_addr
    log_level: str = "INFO"

    def __post_init__(self):
        # logging.basicConfig() requires an uppercase level name
        # ("INFO", not "info") - normalize so either casing works in
        # config.toml.
        self.log_level = self.log_level.upper()


@dataclass
class Config:
    ollama: OllamaConfig
    chunking: ChunkingConfig
    server: ServerConfig
    engine: EngineConfig

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> Config:
        path = Path(path)
        data = tomllib.loads(path.read_text()) if path.exists() else {}

        return cls(
            ollama=OllamaConfig(**data.get("ollama", {})),
            chunking=ChunkingConfig(**data.get("chunking", {})),
            server=ServerConfig(**data.get("server", {})),
            engine=EngineConfig(**data.get("engine", {})),
        )


config = Config.load()
