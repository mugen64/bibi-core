from collections.abc import AsyncIterator

from engines.chunker import chunk_stream
from engines.ollama_engine import OllamaEngine


class EngineManager:
    def __init__(self):
        self.engine = OllamaEngine()

    async def stream_chat_response(
        self,
        prompt: str,
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """
        End-to-end: prompt in, sentence-sized text chunks out.
        This is what the API layer calls - it never sees raw tokens.
        """
        token_stream = self.engine.stream_response(prompt, conversation_history)
        async for chunk in chunk_stream(token_stream):
            yield chunk

    async def health_check(self) -> bool:
        return await self.engine.health_check()

    async def ensure_ready(self) -> None:
        """Raises ModelNotFoundError / OllamaUnreachableError if the
        service can't currently serve a request. Call before streaming."""
        await self.engine.ensure_model_available()



engine_manager = EngineManager()
