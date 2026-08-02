import asyncio
import logging

import uvicorn

from config import HOST, HTTP_PORT
from grpc_server import serve as serve_grpc
from server import get_app

logging.basicConfig(level=logging.INFO)

app = get_app()


async def serve_http():
    uv_config = uvicorn.Config(app, host=HOST, port=HTTP_PORT, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()


async def main():
    await asyncio.gather(
        serve_grpc(),
        serve_http(),
    )


if __name__ == "__main__":
    asyncio.run(main())
