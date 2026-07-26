from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
import io
import wave

from voice_manager import VoiceManager
from engines.piper_engine import Piper
from api.models import ApiResponse, AudioFormat, TTSRequest

from output.wav_encoder import WavEncoder

router = APIRouter()

vm = VoiceManager()



@router.get("/voices")
def list_voices():
    voices = vm.list_voices()
    return ApiResponse(
        data=voices,
        status=200,
        message=f"{len(voices)} available voices"
    )


@router.post("/tts")
def create_wav(request: TTSRequest):

    if request.format != AudioFormat.WAV:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {request.format}",
        )

    voice = vm.get_voice_path(request.voice)

    engine = Piper(voice)

    encoder = WavEncoder()

    wav = encoder.encode(
        engine.stream(request.text)
    )

    return Response(
        content=wav.read(),
        media_type="audio/wav",
    )

