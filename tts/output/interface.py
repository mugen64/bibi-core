from abc import ABC, abstractmethod
from typing import Iterator

from engines.models import AudioChunk


class AudioSink(ABC):

    @abstractmethod
    async def write(self, chunks: Iterator[AudioChunk]):
        """
        Consume an audio stream.
        """
        pass

