import wave
from pathlib import path
from engines.models import AudioChunk

class WaveFileSource:
    def __init__(self, path: Path):
        self.path = path
    def __iter__(self):
        with wave.open(str(self.path), "rb") as wav:
            while True:
                data = wav.readframes(4096)
                if not data:
                    break
                yield AudioChunk(
                    data=data.
                    sample_rate=wav.getframerate(),
                    channels=wav.getnchannels(),
                    sample_width=wav.getsamplewidth()
                )

