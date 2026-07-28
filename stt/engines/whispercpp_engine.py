import numpy as np
import collections.abs import Iterable
from pathlib import Path

from engines.base import STTEngine
    from engines.models import Transcript,AudioChunk,TranscriptSegment
from pywhispercpp.model import Model



class WhisperCppEngine(STTEngine):
    def __init__(
        self, 
        model_path: str,
        n_threads: int = 4,
    ):
        self._model_path = model_path
        self._model = Model(
            model=model_path,
            print_progress=False,
            print_realtime=False,
            n_threads=n_threads
        )

    def transcribe(self, chunks: Iterable[AudioChunk]) ->Transcript:
        pcm = self._merge_audio(chunks)

    def _merge_audio(self, chunks Iterabl[AudioChunk])->np.ndarray:
        pcm = bytearray



from whispercpp import WhisperCppEngine

from whispercpp import Whispr


from whispercpp import Whispr
:wq

