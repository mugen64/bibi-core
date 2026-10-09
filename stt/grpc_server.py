import logging

import grpc
from grpc_reflection.v1alpha import reflection

import stt_pb2
import stt_pb2_grpc
from config import config
from grpc_servicer import SpeechToTextServicer

logger = logging.getLogger(__name__)


async def serve():
    server = grpc.aio.server()
    stt_pb2_grpc.add_SpeechToTextServicer_to_server(SpeechToTextServicer(), server)

    # Enables reflection so tools like grpcurl can discover the service
    # without needing the .proto file passed explicitly - handy for
    # local debugging, low cost to leave enabled in dev.
    service_names = (
        stt_pb2.DESCRIPTOR.services_by_name["SpeechToText"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    addr = f"{config.server.host}:{config.server.grpc_port}"
    server.add_insecure_port(addr)

    logger.info("stt grpc server listening on %s", addr)
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        # Without an explicit stop(), a cancelled/interrupted shutdown
        # leaves this to the Server object's __del__ finalizer, which
        # runs after the event loop is already closed and fails loudly
        # ("Event loop is closed") instead of shutting down cleanly.
        await server.stop(grace=None)
