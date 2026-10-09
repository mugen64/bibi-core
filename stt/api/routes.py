import asyncio
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket

from utils.audio import calculate_duration
from api.models import ApiResponse, transcript_to_response
from config import config
from engine_manager import engine_manager
from engines.audio_sources import WavFileAudioSource, WebSocketAudioSource

router = APIRouter()
sm = engine_manager

@router.get("/models")
def list_voices():
    models = sm.list_models()
    return ApiResponse(
        data=models,
        status=200,
        message=f"{len(models)} available models"
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
        engine = await asyncio.to_thread(sm.get_engine, model)
        script = await asyncio.to_thread(engine.transcribe, src)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return ApiResponse(
        status=200,
        message="Transciption succeeded",
        data=transcript_to_response(script)
    )



@router.websocket("/transcribe-stream")
async def transcribe_stream(
    websocket: WebSocket,
):

    await websocket.accept()


    source = WebSocketAudioSource(
        websocket
    )


    buffer = []


    engine = await asyncio.to_thread(engine_manager.get_engine)

    while True:
 
        chunk = await source.receive_chunk()

        if chunk is None:
            break


        buffer.append(chunk)


        duration = calculate_duration(
            buffer
        )


        if duration >= 5:

            transcript = await asyncio.to_thread(engine.transcribe, list(buffer))


            await websocket.send_json(
                {
                    "text": transcript.text
                }
            )


            buffer.clear()
