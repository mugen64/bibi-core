class LLMServiceError(Exception):
    """Base class for all engine-level errors."""
    code: str = "llm_error"


class ModelNotFoundError(LLMServiceError):
    code = "model_not_found"

    def __init__(self, model: str):
        self.model = model
        super().__init__(
            f"Model '{model}' not found. Try: ollama pull {model}"
        )


class OllamaUnreachableError(LLMServiceError):
    code = "ollama_unreachable"

    def __init__(self):
        super().__init__("Could not reach Ollama - is `ollama serve` running?")


class StreamInterruptedError(LLMServiceError):
    code = "stream_interrupted"

    def __init__(self, reason: str = "connection dropped mid-generation"):
        super().__init__(reason)

