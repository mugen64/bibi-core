from abc import ABC, abstractmethod
from collections.abc import Iterator

from engines.models import AudioChunk


class TTSEngine(ABC):
    @abstractmethod
    def stream(self, text: str) -> Iterator[AudioChunk]:
        """Synthesize text, yielding audio chunks as they're produced."""
        ...
