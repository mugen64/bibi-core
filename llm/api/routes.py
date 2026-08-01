import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.models import ChatRequest, HealthResponse, ApiResponse
from engine_manager import engine_manager

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Returns the full response as a single JSON object.
    This is what the Go gateway calls - it never sees raw tokens.
    """
    history = [m.model_dump() for m in request.conversation_history]
    response_chunks = []
    async for chunk in engine_manager.stream_chat_response(
        request.prompt, history
    ):
        response_chunks.append(chunk)
    return ApiResponse(
        data="".join(response_chunks),
        status=200,
        message="OK",
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streams sentence-sized text chunks as newline-delimited JSON (NDJSON).
    The Go gateway reads this line-by-line and forwards each chunk to TTS
    as it arrives, rather than waiting for the full response.

    NOTE: once proto/llm.proto is written, this becomes a gRPC streaming
    endpoint instead - keeping it as HTTP/NDJSON for now so it's easy to
    test standalone with curl before wiring up gRPC.
    """

    async def generate():
        history = [m.model_dump() for m in request.conversation_history]
        async for chunk in engine_manager.stream_chat_response(
            request.prompt, history
        ):
            yield json.dumps({"type": "chunk", "text": chunk}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/health", response_model=HealthResponse)
async def health():
    reachable = await engine_manager.health_check()
    return HealthResponse(
        status="ok" if reachable else "degraded",
        ollama_reachable=reachable,
    )
