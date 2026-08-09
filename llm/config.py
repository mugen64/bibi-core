"""
Config loader for the llm service.
Mirrors the config.py + config.toml pattern used in stt/ and tts/.

ASSUMPTION: I don't have your actual stt/config.py or tts/config.py in
this environment, so this is a reasonable inference from the file names
in your tree. Replace/adjust to match your real pattern (e.g. if you're
using pydantic-settings, dataclasses, or plain dict loading elsewhere).
"""

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
    log_level: str = "info"


@dataclass
class Config:
    ollama: OllamaConfig
    chunking: ChunkingConfig
    server: ServerConfig

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> "Config":
        path = Path(path)
        data = tomllib.loads(path.read_text()) if path.exists() else {}

        return cls(
            ollama=OllamaConfig(**data.get("ollama", {})),
            chunking=ChunkingConfig(**data.get("chunking", {})),
            server=ServerConfig(**data.get("server", {})),
        )


config = Config.load()
