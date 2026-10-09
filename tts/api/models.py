from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class ApiResponse:
    data: Any
    status: int
    message: str


class AudioFormat(StrEnum):
    WAV = "wav"


class TTSRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=5000,
    )

    voice: str = Field(
        min_length=1,
    )

    format: AudioFormat
