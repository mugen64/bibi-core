from pathlib import Path

from piper import PiperVoice

from engines.base import TTSEngine
from engines.models import AudioChunk
from exceptions import VoiceNotFoundError
from utils.text import strip_markdown


class PiperEngine(TTSEngine):
    @classmethod
    def list_available(cls, directory: Path) -> list[str]:
        voices = []
        for model in directory.glob("*.onnx"):
            config_file = Path(str(model) + ".json")
            if config_file.exists():
                voices.append(model.name)
        return voices

    @classmethod
    def resolve_path(cls, directory: Path, name: str) -> Path:
        voice_path = directory / name
        if not voice_path.is_file():
            raise VoiceNotFoundError(f"Voice not found: {voice_path}")

        json_path = Path(str(voice_path) + ".json")
        if not json_path.exists():
            raise VoiceNotFoundError(f"Missing voice config: {json_path}")

        return voice_path

    def __init__(self, voice_path: Path):
        self.voice_path = voice_path

        if not self.voice_path.exists():
            raise VoiceNotFoundError(f"Voice model not found: {self.voice_path}")

        self.voice = PiperVoice.load(str(self.voice_path))

    def stream(self, text):
        text = strip_markdown(text)
        for chunk in self.voice.synthesize(text):
            yield AudioChunk(
                data=chunk.audio_int16_bytes,
                sample_rate=chunk.sample_rate,
                channels=chunk.sample_channels,
                sample_width=chunk.sample_width,
            )
