from engines.base import STTEngine
from engines.models import Transcript,AudioChunk
from whispercpp import Whispr


class WhisperCppEngine(STTEngine):
    def __init__(self, model_path: str):
        self._model_path = model_path
        self._model = Model(model_path, print_progress=False,print_realtime=False)

    def transcribe(self, chunks: Iterable[AudioChunk]) ->Transcript:
        pass

