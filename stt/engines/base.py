from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from engines.models import AudioChunk, AudioFormatSpec, Transcript


class AudioSource(Protocol):
    """
    Anything that can produce audio chunks
    """

    def __iter__(self) -> Iterator[AudioChunk]: ...


class AsyncAudioSource(Protocol):
    async def receive_chunk(
        self,
    ) -> AudioChunk | None: ...


class STTEngine(ABC):
    @classmethod
    @abstractmethod
    def list_available(cls, directory: Path) -> list[str]:
        """Names of models this provider can load from `directory`."""
        ...

    @classmethod
    @abstractmethod
    def resolve_path(cls, directory: Path, name: str) -> Path:
        """Validate `name` exists under `directory` for this provider's
        file format and return its loadable path. Raises FileNotFoundError
        if it doesn't."""
        ...

    @classmethod
    @abstractmethod
    def required_format(cls) -> AudioFormatSpec | None:
        """Audio format transcribe() requires, or None to accept
        whatever format the audio source already provides."""
        ...

    @abstractmethod
    def transcribe(
        self,
        audio: AudioSource,
    ) -> Transcript:
        """
        transcribe stream of audio chunks
        """
        pass
