import json

from fastapi import APIRouter, HTTPException
from llm.errors import ModelNotFoundError, OllamaUnreachableError, LLMServiceError
import asyncio
from fastapi.responses import StreamingResponse

from api.models import ChatRequest, HealthResponse, ApiResponse
from engine_manager import engine_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    if len(request.prompt) == 0:
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": "Prompt is required"})

    try:
        await engine_manager.ensure_ready()
    except ModelNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.code, "message": str(e)})
    except OllamaUnreachableError as e:
        raise HTTPException(status_code=503, detail={"code": e.code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "unexpected", "message": str(e)})

    history = [m.model_dump() for m in request.conversation_history]
    response_chunks = []

    history = [m.model_dump() for m in request.conversation_history]
    # append system prompt to the beginning of the history
    history.insert(0, {"role": "system", "content": "You are a helpful assistant. Answer as concisely as possible. If you don't know the answer, say 'I don't know'. Do not make up answers. If the user asks for a list, provide a numbered list. If the user asks for a code snippet, provide a code block. If the user asks for a table, provide a markdown table. If the user asks for a summary, provide a concise summary."})
    try:
        
        async for chunk in engine_manager.stream_chat_response(
            request.prompt, history
        ):
            response_chunks.append({"type": "chunk", "text": chunk})

        response_chunks.append({"type": "done"})

    except LLMServiceError as e:
        # Generation started successfully (200 already sent) but broke
        # partway through - headers are committed, so the error has to
        # travel as a line inside the stream, not an HTTP status code.
        logger.warning("Stream failed mid-generation: %s", e)
        yield json.dumps({"type": "error", "code": e.code, "message": str(e)}) + "\n"

    except asyncio.CancelledError:
        # Client (Go gateway) disconnected early - e.g. user interrupted
        # with barge-in. Not an error, just clean up quietly.
        logger.info("Client disconnected mid-stream, stopping generation")
        raise

    except Exception as e:
        # Catch-all so an unexpected bug never leaves the gateway
        # hanging on a connection that dies with no explanation.
        logger.exception("Unexpected error during generation")
        yield json.dumps(
            {"type": "error", "code": "internal_error", "message": str(e)}
            ) + "\n"
    
    return ApiResponse(
        data=response_chunks,
        status=200,
        message="OK",
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streams sentence-sized text chunks as newline-delimited JSON (NDJSON).
    The Go gateway reads this line-by-line and forwards each chunk to TTS
    as it arrives, rather than waiting for the full response.

    Line types the gateway should handle:
      {"type": "chunk", "text": "..."}                  - forward to TTS
      {"type": "done"}                                    - stream finished normally
      {"type": "error", "code": "...", "message": "..."}  - stop, surface to user

    NOTE: once proto/llm.proto is written, this becomes a gRPC streaming
    endpoint instead - keeping it as HTTP/NDJSON for now so it's easy to
    test standalone with curl before wiring up gRPC.
    """
    try:
        await engine_manager.ensure_ready()
    except ModelNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": e.code, "message": str(e)})
    except OllamaUnreachableError as e:
        raise HTTPException(status_code=503, detail={"code": e.code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "unexpected", "message": str(e)})

    async def generate():
        history = [m.model_dump() for m in request.conversation_history]
        try:
            async for chunk in engine_manager.stream_chat_response(
                request.prompt, history
            ):
                yield json.dumps({"type": "chunk", "text": chunk}) + "\n"

            yield json.dumps({"type": "done"}) + "\n"

        except LLMServiceError as e:
            # Generation started successfully (200 already sent) but broke
            # partway through - headers are committed, so the error has to
            # travel as a line inside the stream, not an HTTP status code.
            logger.warning("Stream failed mid-generation: %s", e)
            yield json.dumps({"type": "error", "code": e.code, "message": str(e)}) + "\n"

        except asyncio.CancelledError:
            # Client (Go gateway) disconnected early - e.g. user interrupted
            # with barge-in. Not an error, just clean up quietly.
            logger.info("Client disconnected mid-stream, stopping generation")
            raise

        except Exception as e:
            # Catch-all so an unexpected bug never leaves the gateway
            # hanging on a connection that dies with no explanation.
            logger.exception("Unexpected error during generation")
            yield json.dumps(
                {"type": "error", "code": "internal_error", "message": str(e)}
            ) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

@router.get("/health", response_model=HealthResponse)
async def health():
    reachable = await engine_manager.health_check()
    return HealthResponse(
        status="ok" if reachable else "degraded",
        ollama_reachable=reachable,
    )
