from dataclasses import dataclass


@dataclass
class AudioChunk:
    data: bytes
    sample_rate: int
    channels: int
    sample_width: int


@dataclass(frozen=True)
class AudioFormatSpec:
    """The exact format an STTEngine provider's transcribe() requires."""

    sample_rate: int
    channels: int
    sample_width: int


@dataclass
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    score: float | None


@dataclass
class Transcript:
    segments: list[TranscriptSegment]
    lang: str | None = None

    @property
    def text(self):
        return "".join(seg.text for seg in self.segments)
