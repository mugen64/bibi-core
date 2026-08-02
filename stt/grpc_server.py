import asyncio
import logging

import grpc

import stt_pb2_grpc
from config import HOST, GRPC_PORT
from grpc_servicer import SpeechToTextServicer
from grpc_reflection.v1alpha import reflection
import stt_pb2
import stt_pb2_grpc
from config import HOST, GRPC_PORT


logger = logging.getLogger(__name__)


async def serve():
    server = grpc.aio.server()
    stt_pb2_grpc.add_SpeechToTextServicer_to_server(
        SpeechToTextServicer(), server
    )

    # Enables reflection so tools like grpcurl can discover the service
    # without needing the .proto file passed explicitly - handy for
    # local debugging, low cost to leave enabled in dev.
    service_names = (
        stt_pb2.DESCRIPTOR.services_by_name["SpeechToText"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    addr = f"{HOST}:{GRPC_PORT}"
    server.add_insecure_port(addr)

    logger.info("stt grpc server listening on %s", addr)
    await server.start()
    await server.wait_for_termination()
