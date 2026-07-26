import wave
from pathlib import Path
from piper import PiperVoice
from engines.models import AudioChunk


class Piper:
    def __init__(self, voice_path: Path):
        self.voice_path = voice_path

        if not self.voice_path.exists():
            raise FileNotFoundError(
                f"Voice model not found: {self.voice_path}"
            )

        self.voice = PiperVoice.load(str(self.voice_path))


    def stream(self, text):
        for chunk in self.voice.synthesize(text):
            yield AudioChunk(
                data=chunk.audio_int16_bytes,
                sample_rate=chunk.sample_rate,
                channels=chunk.sample_channels,
                sample_width=chunk.sample_width,
            )
