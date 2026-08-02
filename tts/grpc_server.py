import logging

import grpc
from grpc_reflection.v1alpha import reflection

import tts_pb2
import tts_pb2_grpc
from config import HOST, GRPC_PORT
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

    addr = f"{HOST}:{GRPC_PORT}"
    server.add_insecure_port(addr)
    logger.info("tts grpc server listening on %s", addr)
    await server.start()
    await server.wait_for_termination()
