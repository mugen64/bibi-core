"""
Implements the generated SpeechToTextServicer interface, using the
existing STTManager / WhisperCppEngine under the hood. Buffers incoming
audio chunks and calls engine.transcribe() (a blocking call) via
asyncio.to_thread so it doesn't block the gRPC event loop.
"""

import asyncio
import logging

import grpc

import stt_pb2
import stt_pb2_grpc
from audio_utils import calculate_duration
from engines.models import AudioChunk
from engine_manager import stt_manager  # ASSUMPTION: adjust import path/name to match your actual module
from pb_convert import chunk_from_proto, error_event, transcript_to_event

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 5.0  # matches the threshold already used in routes.py


class SpeechToTextServicer(stt_pb2_grpc.SpeechToTextServicer):
    async def StreamTranscribe(self, request_iterator, context):
        buffer: list[AudioChunk] = []

        try:
            engine = stt_manager.get_engine()  # default model for now
        except FileNotFoundError as e:
            yield error_event("model_not_found", str(e))
            return

        try:
            async for msg in request_iterator:
                if context.cancelled():
                    logger.info("client cancelled stream, stopping")
                    return

                buffer.append(chunk_from_proto(msg))
                duration = calculate_duration(buffer)

                if duration >= WINDOW_SECONDS or msg.end_of_utterance:
                    if buffer:
                        # engine.transcribe() is a blocking call
                        # (pywhispercpp) - run off the event loop
                        transcript = await asyncio.to_thread(
                            engine.transcribe, buffer
                        )
                        event_type = (
                            stt_pb2.TranscriptEvent.FINAL
                            if msg.end_of_utterance
                            else stt_pb2.TranscriptEvent.PARTIAL
                        )
                        yield transcript_to_event(transcript, event_type)
                        buffer.clear()

                if msg.end_of_utterance:
                    return

        except ValueError as e:
            # raised by WhisperCppEngine._validate_chunk on mismatched
            # sample rate/channels/width across chunks
            logger.warning("invalid audio format: %s", e)
            yield error_event("invalid_audio_format", str(e))

        except Exception as e:
            logger.exception("unexpected error in StreamTranscribe")
            yield error_event("internal_error", str(e))

    async def HealthCheck(self, request, context):
        try:
            models = stt_manager.list_models()
            return stt_pb2.HealthResponse(
                healthy=len(models) > 0,
                model_loaded=stt_manager._default_model,
            )
        except Exception as e:
            logger.exception("health check failed")
            return stt_pb2.HealthResponse(healthy=False, model_loaded="")
