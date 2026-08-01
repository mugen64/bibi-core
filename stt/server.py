from fastapi import FastAPI

from api.routes import router


app = FastAPI(
    title="Bibi STT",
    version="0.1.0",
)

app.include_router(router)


def get_app() -> FastAPI:
    return app