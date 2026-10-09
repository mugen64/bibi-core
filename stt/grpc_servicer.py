"""
Implements the generated SpeechToTextServicer interface, using the
existing EngineManager / WhisperCppEngine under the hood. Buffers incoming
audio chunks and calls engine.transcribe() (a blocking call) via
asyncio.to_thread so it doesn't block the gRPC event loop.
"""

import asyncio
import logging

import stt_pb2
import stt_pb2_grpc
from engine_manager import engine_manager
from engines.models import AudioChunk
from exceptions import InvalidAudioFormatError, ModelNotFoundError
from pb_convert import chunk_from_proto, error_event, transcript_to_event
from utils.audio import calculate_duration

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 5.0  # matches the threshold already used in routes.py


class SpeechToTextServicer(stt_pb2_grpc.SpeechToTextServicer):
    async def StreamTranscribe(self, request_iterator, context):
        buffer: list[AudioChunk] = []

        try:
            with engine_manager.acquire_engine() as engine:  # default model for now
                async for msg in request_iterator:
                    if context.cancelled():
                        logger.info("client cancelled stream, stopping")
                        return

                    buffer.append(chunk_from_proto(msg))
                    duration = calculate_duration(buffer)

                    if (duration >= WINDOW_SECONDS or msg.end_of_utterance) and buffer:
                        # engine.transcribe() is a blocking call (pywhispercpp) -
                        # run off the event loop
                        prepared = list(engine_manager.prepare_audio(buffer))
                        transcript = await asyncio.to_thread(
                            engine.transcribe, prepared
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

        except ModelNotFoundError as e:
            yield error_event(e.code, str(e))

        except InvalidAudioFormatError as e:
            # raised by WhisperCppEngine._validate_chunk on mismatched
            # sample rate/channels/width across chunks
            logger.warning("invalid audio format: %s", e)
            yield error_event(e.code, str(e))

        except Exception as e:
            logger.exception("unexpected error in StreamTranscribe")
            yield error_event("internal_error", str(e))

    async def HealthCheck(self, request, context):
        try:
            models = engine_manager.list_models()
            return stt_pb2.HealthResponse(
                healthy=len(models) > 0,
                model_loaded=engine_manager.default_model,
            )
        except Exception:
            logger.exception("health check failed")
            return stt_pb2.HealthResponse(healthy=False, model_loaded="")
