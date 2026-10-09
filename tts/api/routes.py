from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import Response

from api.models import ApiResponse, AudioFormat, TTSRequest
from engine_manager import engine_manager
from exceptions import VoiceNotFoundError
from output.http import HttpAudioSink
from output.wav_encoder import WavEncoder
from utils.async_io import iter_in_thread

router = APIRouter()

vm = engine_manager


@router.get("/voices")
def list_voices():
    voices = vm.list_voices()
    return ApiResponse(
        data=voices, status=200, message=f"{len(voices)} available voices"
    )


@router.post("/tts")
def create_wav(request: TTSRequest):

    if request.format != AudioFormat.WAV:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {request.format}",
        )

    try:
        with engine_manager.acquire_engine(request.voice) as engine:
            wav = WavEncoder().encode(engine.stream(request.text))
    except VoiceNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=wav.read(),
        media_type="audio/wav",
    )


@router.websocket("/tts-stream")
async def tts_stream(websocket: WebSocket):

    await websocket.accept()

    try:
        request = await websocket.receive_json()
        text = request.get("text", "")
        if not isinstance(text, str) or not text.strip():
            await websocket.close(code=1008, reason="text is required")
            return

        async with engine_manager.aacquire_engine(request.get("voice")) as piper:
            sink = HttpAudioSink(websocket)
            await sink.write(iter_in_thread(piper.stream, text))
    except (VoiceNotFoundError, TypeError) as exc:
        await websocket.close(code=1008, reason=str(exc))
        return

    await websocket.close()
