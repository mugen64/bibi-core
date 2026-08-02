from models import AudioChunk, Transcript, TranscriptSegment
import stt_pb2


def chunk_from_proto(msg: stt_pb2.AudioChunkMsg) -> AudioChunk:
    return AudioChunk(
        data=msg.data,
        sample_rate=msg.sample_rate,
        channels=msg.channels,
        sample_width=msg.sample_width,
    )


def transcript_to_proto(t: Transcript, event_type: int) -> stt_pb2.TranscriptEvent:
    return stt_pb2.TranscriptEvent(
        type=event_type,
        segments=[
            stt_pb2.TranscriptSegmentMsg(
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=s.text,
                score=s.score if s.score is not None else None,
            )
            for s in t.segments
        ],
        lang=t.lang,
    )
