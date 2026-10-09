import logging

import grpc
from grpc_reflection.v1alpha import reflection

import tts_pb2
import tts_pb2_grpc
from config import config
from grpc_servicer import TextToSpeechServicer

logger = logging.getLogger(__name__)


async def serve():
    server = grpc.aio.server()
    tts_pb2_grpc.add_TextToSpeechServicer_to_server(TextToSpeechServicer(), server)

    service_names = (
        tts_pb2.DESCRIPTOR.services_by_name["TextToSpeech"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    addr = f"{config.server.host}:{config.server.grpc_port}"
    server.add_insecure_port(addr)
    logger.info("tts grpc server listening on %s", addr)
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        # Without an explicit stop(), a cancelled/interrupted shutdown
        # leaves this to the Server object's __del__ finalizer, which
        # runs after the event loop is already closed and fails loudly
        # ("Event loop is closed") instead of shutting down cleanly.
        await server.stop(grace=None)
