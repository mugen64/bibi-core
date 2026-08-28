from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    data: Any
    status: int
    message: str



class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    prompt: str
    conversation_history: list[ChatMessage] = Field(default_factory=list)


class ChatChunkResponse(BaseModel):
    """One sentence-sized chunk, streamed as newline-delimited JSON."""
    type: str = "chunk"
    text: str


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
