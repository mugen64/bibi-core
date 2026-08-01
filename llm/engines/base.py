from abc import ABC, abstractmethod
from engines.models import AudioChunk, Transcript
from typing import Protocol, Iterator

class AudioSource(Protocol):
    """
    Anything that can produce audio chunks
    """
    def __iter__(self) -> Iterator[AudioChunk]:
        ...

class AsyncAudioSource(Protocol):

    async def receive_chunk(
        self,
    ) -> AudioChunk | None:
        ...

class STTEngine(ABC):

    @abstractmethod
    def transcribe(
            self,
            audio: AudioSource,
    )->Transcript: 
        """
        transcribe stream of audio chunks
        """
        pass
