from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from engines.models import AudioChunk


class TTSEngine(ABC):
    @classmethod
    @abstractmethod
    def list_available(cls, directory: Path) -> list[str]:
        """Names of voices this provider can load from `directory`."""
        ...

    @classmethod
    @abstractmethod
    def resolve_path(cls, directory: Path, name: str) -> Path:
        """Validate `name` exists under `directory` for this provider's
        file format and return its loadable path. Raises FileNotFoundError
        if it doesn't."""
        ...

    @abstractmethod
    def stream(self, text: str) -> Iterator[AudioChunk]:
        """Synthesize text, yielding audio chunks as they're produced."""
        ...
