from fastapi import FastAPI

from api.routes import router
from config import config

app = FastAPI(
    title="bibi-llm"
)
app.include_router(router)


def get_app() -> FastAPI:
    return app
