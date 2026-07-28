from abc import ABC, abstractmethod
from engines.models import AudioChunk, Transcript
from typing import Protocol, Iterator

class AudioSource(Protocol):
    def __iter__(self) -> Iterator["AudioChunk"]

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
