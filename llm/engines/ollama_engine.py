"""
Thin wrapper around the Ollama Python client.

Kept deliberately small: this file's only job is "talk to Ollama and
yield tokens as they arrive." Sentence-chunking logic lives separately
in chunker.py so this stays swappable if you ever add another backend.
"""

from collections.abc import AsyncIterator

import ollama

from config import config


class OllamaEngine:
    def __init__(self):
        self.client = ollama.AsyncClient(host=config.ollama.host)
        self.model = config.ollama.model

    async def stream_response(
        self,
        prompt: str,
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """
        Yields raw text tokens as Ollama generates them.
        conversation_history: list of {"role": "user"|"assistant", "content": str}
        """
        messages = (conversation_history or []) + [
            {"role": "user", "content": prompt}
        ]

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

    async def health_check(self) -> bool:
        try:
            await self.client.list()
            return True
        except Exception:
            return False
