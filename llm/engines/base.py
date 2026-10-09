from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMEngine(ABC):
    @abstractmethod
    async def ensure_model_available(self) -> None:
        """Raises if the backend/model isn't ready to serve a request."""
        ...

    @abstractmethod
    def stream_response(
        self,
        prompt: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Yields raw text tokens as they're generated."""
        ...

    @abstractmethod
    async def health_check(self) -> bool: ...
