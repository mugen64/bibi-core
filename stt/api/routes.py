from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import StreamingResponse, Response

from engine_manager import STTManager

sm = STTManager()

@router.get("/models")
def list_voices():
    voices = vm.list_voices()
    return ApiResponse(
        data=voices,
        status=200,
        message=f"{len(voices)} available voices"
    )

