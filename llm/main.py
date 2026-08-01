import uvicorn

from config import config
from server import get_app

app = get_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level,
        reload=True,
    )
