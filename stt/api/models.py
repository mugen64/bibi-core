import math

from dataclasses import dataclass
from typing import Any
from enum import Enum

from pydantic import BaseModel, Field
from engines.models import Transcript,TranscriptSegment



@dataclass
class ApiResponse:
    data: Any
    status: int
    message: str


class AudioFormat(str, Enum):
    WAV = "wav"

class SegmentResponse(BaseModel):
    start_ms: int
    end_ms: int
    score: float | None
    text: str


class TranscriptionResponse(BaseModel):
    segments:list[SegmentResponse]

def transcript_to_response(transcript: Transcript)-> TranscriptionResponse:
    return TranscriptionResponse(
        segments=[
            SegmentResponse(
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=s.text,
                score=clean_nan(s.score)
            )
            for s in transcript.segments
        ]
    )

def clean_nan(obj):
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj
