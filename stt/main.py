from config import MODEL_DIR, DEFAULT_MODEL
from engine_manager import STTManager
from engines.audio_sources import WavFileAudioSource

from server import get_app

app = get_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5001,
    )

