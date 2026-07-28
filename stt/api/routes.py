from fastapi import APIRouter, HTTPException, WebSocket,Form,File,UploadFile
from fastapi.responses import StreamingResponse, Response

from api.models import ApiResponse,transcript_to_response
from engine_manager import STTManager
from config import DEFAULT_MODEL
from engines.audio_sources import WavFileAudioSource

router = APIRouter()
sm = STTManager()

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
            file: UploadFile=File(...),
            model: str=None,
):
    print(file.content_type)
    if file.content_type != "audio/wav":
        raise HTTPException(
            status_code=400,
            detail="Only wav files are supported",
        )
    if model is None:
        model = DEFAULT_MODEL

    temp_file = f"/tmp/{file.filename}"
    with open(temp_file, "wb") as f:
        f.write(await file.read())

    src = WavFileAudioSource(temp_file)
    engine = sm.get_engine(model)

    script = engine.transcribe(src)

    return ApiResponse(
        status=200,
        message="Transciption succeeded",
        data=transcript_to_response(script)
    )
