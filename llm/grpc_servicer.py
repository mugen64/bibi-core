"""
Implements the generated LLMChat servicer. Thin wrapper around
engine_manager - all the actual chunking/streaming logic stays exactly
as it was for the HTTP route, just exposed over gRPC here instead.
"""

import logging

import grpc

import llm_pb2
import llm_pb2_grpc
from engine_manager import engine_manager
from exceptions import LLMServiceError, ModelNotFoundError, OllamaUnreachableError

logger = logging.getLogger(__name__)


class LLMChatServicer(llm_pb2_grpc.LLMChatServicer):
    async def StreamChat(self, request, context):
        # Pre-flight check before streaming anything - for a unary-request/
        # streaming-response RPC, we can still bail out cleanly here since
        # no response has been sent yet (unlike a bidi stream already in
        # progress). context.abort() sets a proper gRPC status code, which
        # is the equivalent of the HTTP 404/503 we used in the REST route.
        try:
            await engine_manager.ensure_ready()
        except ModelNotFoundError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
            return
        except OllamaUnreachableError as e:
            await context.abort(grpc.StatusCode.UNAVAILABLE, str(e))
            return

        history = [
            {"role": m.role, "content": m.content}
            for m in request.conversation_history
        ]

        try:
            async for chunk in engine_manager.stream_chat_response(
                request.prompt, history
            ):
                if context.cancelled():
                    logger.info("client cancelled stream, stopping generation")
                    return
                yield llm_pb2.ChatEvent(type=llm_pb2.ChatEvent.CHUNK, text=chunk)

            yield llm_pb2.ChatEvent(type=llm_pb2.ChatEvent.DONE)

        except LLMServiceError as e:
            # Generation already started (stream is open) - same as the
            # HTTP version, the error has to travel as a message on the
            # stream rather than a status code at this point.
            logger.warning("stream failed mid-generation: %s", e)
            yield llm_pb2.ChatEvent(
                type=llm_pb2.ChatEvent.ERROR,
                error_code=e.code,
                error_message=str(e),
            )

        except Exception as e:
            logger.exception("unexpected error during generation")
            yield llm_pb2.ChatEvent(
                type=llm_pb2.ChatEvent.ERROR,
                error_code="internal_error",
                error_message=str(e),
            )

    async def HealthCheck(self, request, context):
        reachable = await engine_manager.health_check()
        return llm_pb2.HealthResponse(
            healthy=reachable,
            ollama_reachable=reachable,
        )
