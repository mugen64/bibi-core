"""
Converts between generated protobuf messages (the wire format) and our
own domain dataclasses (models.py) used internally in business logic.
Keeps whisper.cpp/engine code completely unaware of protobuf.
"""

import stt_pb2
from engines.models import AudioChunk, Transcript, TranscriptSegment


def chunk_from_proto(msg: stt_pb2.AudioChunkMsg) -> AudioChunk:
    return AudioChunk(
        data=msg.data,
        sample_rate=msg.sample_rate,
        channels=msg.channels,
        sample_width=msg.sample_width,
    )


def segment_to_proto(seg: TranscriptSegment) -> stt_pb2.TranscriptSegmentMsg:
    kwargs = {
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "text": seg.text,
    }
    if seg.score is not None:
        kwargs["score"] = seg.score
    return stt_pb2.TranscriptSegmentMsg(**kwargs)


def transcript_to_event(
    transcript: Transcript,
    event_type: "stt_pb2.TranscriptEvent.EventType",
) -> stt_pb2.TranscriptEvent:
    kwargs = {
        "type": event_type,
        "segments": [segment_to_proto(s) for s in transcript.segments],
    }
    if transcript.lang is not None:
        kwargs["lang"] = transcript.lang
    return stt_pb2.TranscriptEvent(**kwargs)


def error_event(code: str, message: str) -> stt_pb2.TranscriptEvent:
    return stt_pb2.TranscriptEvent(
        type=stt_pb2.TranscriptEvent.ERROR,
        error_code=code,
        error_message=message,
    )

