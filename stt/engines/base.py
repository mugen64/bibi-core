from abc import ABC, abstractmethod
from engines.models import AudioChunk, Transcript

class STTEngine(ABC):

    @abstractmethod
    def transcribe(
            self,
            audio: Iterable[AudioChunk],
    )->Transcript: 
        """
        transcribe stream of audio chunks
        """
        pass
