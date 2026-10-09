import asyncio
import logging

import uvicorn

from config import config
from grpc_server import serve as serve_grpc
from server import get_app

logging.basicConfig(level=config.server.log_level)
logger = logging.getLogger(__name__)

app = get_app()


async def serve_http():
    uv_config = uvicorn.Config(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level.lower(),
    )
    server = uvicorn.Server(uv_config)
    await server.serve()


async def main():
    await asyncio.gather(
        serve_grpc(),
        serve_http(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # uvicorn re-raises SIGINT as a KeyboardInterrupt inside the
        # event loop (it expects to own the loop outright) - without
        # this, Ctrl+C prints a full traceback and exits non-zero even
        # though the shutdown itself is clean.
        logger.info("shutdown requested, exiting")
