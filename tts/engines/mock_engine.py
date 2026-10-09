"""
Deterministic stand-in for PiperEngine - no real voice model required.
Useful for exercising the HTTP/gRPC synthesis pipeline without Piper
voice files installed.
"""

from collections.abc import Iterator
from pathlib import Path

from engines.base import TTSEngine
from engines.models import AudioChunk

_SAMPLE_RATE = 22050


class MockEngine(TTSEngine):
    @classmethod
    def list_available(cls, directory: Path) -> list[str]:
        return ["mock"]

    @classmethod
    def resolve_path(cls, directory: Path, name: str) -> Path:
        # No real file backs this provider - nothing to validate.
        return directory / name

    def __init__(self, voice_path: Path):
        self.voice_path = voice_path

    def stream(self, text: str) -> Iterator[AudioChunk]:
        # One short burst of silence, sized to the input text, just
        # enough to exercise the audio pipeline end-to-end.
        n_samples = max(_SAMPLE_RATE // 10, len(text) * 200)
        yield AudioChunk(
            data=b"\x00\x00" * n_samples,
            sample_rate=_SAMPLE_RATE,
            channels=1,
            sample_width=2,
        )
