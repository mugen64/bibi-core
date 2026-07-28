from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import StreamingResponse, Response

from api.models import ApiResponse
from engine_manager import STTManager

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

