"""
Thin wrapper around the Ollama Python client.

Kept deliberately small: this file's only job is "talk to Ollama and
yield tokens as they arrive." Sentence-chunking logic lives separately
in chunker.py so this stays swappable if you ever add another backend.
"""

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import ollama

from config import config
from engines.base import LLMEngine
from exceptions import (
    ModelNotFoundError,
    OllamaUnreachableError,
    StreamInterruptedError,
)

logger = logging.getLogger(__name__)


class OllamaEngine(LLMEngine):
    def __init__(self):
        self.client: ollama.AsyncClient = ollama.AsyncClient(host=config.ollama.host)
        self.model: str = config.ollama.model
        # Monotonic timestamp of the last successful ensure_model_available()
        # check - lets us skip the Ollama round-trip on every request.
        self._last_checked_at: float | None = None

    async def models(self) -> set[str]:
        try:
            models = await self.client.list()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise OllamaUnreachableError() from e

        return {m["model"] for m in models.get("models", [])}

    async def ensure_model_available(self) -> None:
        """
        Pre-flight check - call this BEFORE opening a streaming response,
        so failures surface as a normal HTTP error code rather than a
        broken stream. Raises ModelNotFoundError or OllamaUnreachableError.

        A successful check is cached for availability_cache_seconds, so a
        burst of requests doesn't each pay a round-trip to Ollama. Failures
        are never cached - always re-checked immediately.
        """
        now = time.monotonic()
        ttl = config.ollama.availability_cache_seconds
        if self._last_checked_at is not None and (now - self._last_checked_at) < ttl:
            return

        try:
            models = await self.client.list()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise OllamaUnreachableError() from e

        available = {m["model"] for m in models.get("models", [])}
        # Ollama model names sometimes include/omit the ":latest" tag -
        # check both forms so "llama3.1" matches "llama3.1:latest".
        matches = any(
            self.model == m or self.model == m.split(":")[0] for m in available
        )
        if not matches:
            raise ModelNotFoundError(self.model)

        self._last_checked_at = now

    async def stream_response(
        self,
        prompt: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """
        Yields raw text tokens as Ollama generates them.
        conversation_history: list of {"role": "user"|"assistant", "content": str}

        Raises StreamInterruptedError if the connection drops partway
        through generation (network blip, Ollama restart, etc).
        """
        messages = (conversation_history or []) + [{"role": "user", "content": prompt}]

        try:
            stream = await self.client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": config.ollama.temperature,
                    "num_ctx": config.ollama.context_window,
                },
                keep_alive=config.ollama.keep_alive,
            )

            async for chunk in stream:
                token = chunk["message"]["content"]
                if token:
                    yield token

        except ollama.ResponseError as e:
            # Model existed at pre-flight but got unloaded/deleted mid-request
            if e.status_code == 404:
                raise ModelNotFoundError(self.model) from e
            raise StreamInterruptedError(str(e)) from e

        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            # Ollama process died, network dropped, or connection reset
            # partway through streaming tokens
            raise StreamInterruptedError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            lls = await self.client.list()
            logger.info("found %d models", len(lls.models))
            return True
        except Exception:
            return False
