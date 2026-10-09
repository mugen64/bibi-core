import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket

from api.models import ApiResponse, transcript_to_response
from config import config
from engine_manager import engine_manager
from engines.audio_sources import WavFileAudioSource, WebSocketAudioSource
from exceptions import InvalidAudioFormatError, ModelNotFoundError
from utils.audio import calculate_duration

router = APIRouter()


@router.get("/models")
def list_models():
    models = engine_manager.list_models()
    return ApiResponse(
        data=models, status=200, message=f"{len(models)} available models"
    )


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    model: str | None = None,
):
    if file.content_type not in {"audio/wav", "audio/x-wav"}:
        raise HTTPException(
            status_code=400,
            detail="Only wav files are supported",
        )
    if model is None:
        model = config.models.default

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = temp_file.name
            while chunk := await file.read(1024 * 1024):
                temp_file.write(chunk)

        src = WavFileAudioSource(temp_path)

        def _transcribe():
            with engine_manager.acquire_engine(model) as engine:
                return engine.transcribe(engine_manager.prepare_audio(src))

        script = await asyncio.to_thread(_transcribe)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except InvalidAudioFormatError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    finally:
        await file.close()
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)

    return ApiResponse(
        status=200,
        message="Transcription succeeded",
        data=transcript_to_response(script),
    )


@router.websocket("/transcribe-stream")
async def transcribe_stream(
    websocket: WebSocket,
):

    await websocket.accept()

    source = WebSocketAudioSource(websocket)

    buffer = []

    try:
        with engine_manager.acquire_engine() as engine:
            while True:
                chunk = await source.receive_chunk()

                if chunk is None:
                    break

                buffer.append(chunk)

                duration = calculate_duration(buffer)

                if duration >= 5:
                    prepared = list(engine_manager.prepare_audio(buffer))
                    transcript = await asyncio.to_thread(engine.transcribe, prepared)

                    await websocket.send_json({"text": transcript.text})

                    buffer.clear()
    except (ModelNotFoundError, InvalidAudioFormatError) as exc:
        await websocket.close(code=1008, reason=str(exc))
