import logging

import grpc

import tts_pb2
import tts_pb2_grpc
from async_utils import iter_in_thread
from engines.piper_engine import Piper
from voice_manager import voice_manager  # see singleton change below

logger = logging.getLogger(__name__)


class TextToSpeechServicer(tts_pb2_grpc.TextToSpeechServicer):
    async def StreamSynthesize(self, request, context):
       
        try:
        
            with voice_manager.acquire_engine(request.voice or None) as engine:
                async for chunk in iter_in_thread(engine.stream, request.text):
                    if context.cancelled():
                        logger.info("client cancelled stream, stopping synthesis")
                        return
                    yield tts_pb2.AudioChunkMsg(
                        data=chunk.data,
                        sample_rate=chunk.sample_rate,
                        channels=chunk.channels,
                        sample_width=chunk.sample_width,
                    )
        except FileNotFoundError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            # Unlike the HTTP+NDJSON pattern used for llm/, gRPC status
            # codes are sent as trailers (after all messages), so we
            # CAN abort with a proper status even mid-stream - no need
            # for an in-band error message type here.
            logger.exception("tts synthesis failed")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def HealthCheck(self, request, context):
        try:
            voices = voice_manager.list_voices()
            return tts_pb2.HealthResponse(healthy=True, voices_available=voices)
        except Exception:
            logger.exception("health check failed")
            return tts_pb2.HealthResponse(healthy=False, voices_available=[])
