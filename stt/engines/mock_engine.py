"""
Deterministic stand-in for WhisperCppEngine - no real model required.
Useful for exercising the HTTP/gRPC transcription pipeline without a
whisper.cpp model installed.
"""

from pathlib import Path

from engines.base import AudioSource, STTEngine
from engines.models import AudioFormatSpec, Transcript, TranscriptSegment
from utils.audio import calculate_duration


class MockSTTEngine(STTEngine):
    @classmethod
    def list_available(cls, directory: Path) -> list[str]:
        return ["mock"]

    @classmethod
    def resolve_path(cls, directory: Path, name: str) -> Path:
        # No real file backs this provider - nothing to validate.
        return directory / name

    @classmethod
    def required_format(cls) -> AudioFormatSpec | None:
        return None

    def __init__(self, model_path: Path):
        self._model_path = model_path

    def transcribe(self, audio: AudioSource) -> Transcript:
        chunks = list(audio)
        duration = calculate_duration(chunks)
        return Transcript(
            segments=[
                TranscriptSegment(
                    start_ms=0,
                    end_ms=int(duration * 1000),
                    text=f"[mock transcript, {duration:.1f}s of audio]",
                    score=1.0,
                )
            ]
        )
