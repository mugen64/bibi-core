"""
Deterministic stand-in for OllamaEngine - no network calls, no real
model. Useful for local dev and for exercising the HTTP/gRPC streaming
pipeline without an Ollama install.
"""

from collections.abc import AsyncIterator
from typing import Any

from engines.base import LLMEngine


class MockEngine(LLMEngine):
    async def ensure_model_available(self) -> None:
        return

    async def stream_response(
        self,
        prompt: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        for word in f"You said: {prompt}".split(" "):
            yield word + " "

    async def health_check(self) -> bool:
        return True
