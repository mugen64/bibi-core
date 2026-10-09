class STTServiceError(Exception):
    """Base class for all engine-level errors."""

    code: str = "stt_error"


class ModelNotFoundError(STTServiceError):
    code = "model_not_found"

    def __init__(self, model: str):
        self.model = model
        super().__init__(f"Unknown model '{model}'")


class InvalidAudioFormatError(STTServiceError):
    code = "invalid_audio_format"
