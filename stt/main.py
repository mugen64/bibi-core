import asyncio
import logging

import uvicorn

from config import config
from engine_manager import stt_manager
from grpc_server import serve as serve_grpc
from server import get_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = get_app()


async def serve_http():
    uv_config = uvicorn.Config(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level="info",
    )
    server = uvicorn.Server(uv_config)
    await server.serve()


async def main():
    # Warm up the default model at startup rather than paying the load
    # cost on the first real request (HTTP, WS, or gRPC - whichever
    # arrives first). get_engine() is blocking, but this runs once
    # before either server starts accepting traffic, so it's fine here.
    logger.info("loading default model '%s'...", config.models.default)
    stt_manager.get_engine()
    logger.info("model loaded, starting servers")

    # Run gRPC (Go gateway traffic) and HTTP (manual testing / health)
    # concurrently. If either crashes, gather() takes both down - a
    # half-running service is a confusing state to leave running.
    await asyncio.gather(
        serve_grpc(),
        serve_http(),
    )


if __name__ == "__main__":
    asyncio.run(main())
