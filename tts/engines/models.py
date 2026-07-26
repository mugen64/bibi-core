from dataclasses import dataclass

@dataclass
class AudioChunk:
    data: bytes
    sample_rate: int
    channels: int
    sample_width: int

