from pydantic import BaseModel

from dataclasses import dataclass
from typing import Any
from enum import Enum


class ApiResponse(BaseModel):
    data: Any
    status: int
    message: str



class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    prompt: str
    conversation_history: list[ChatMessage] = []


class ChatChunkResponse(BaseModel):
    """One sentence-sized chunk, streamed as newline-delimited JSON."""
    type: str = "chunk"
    text: str


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
