class TTSServiceError(Exception):
    """Base class for all engine-level errors."""

    code: str = "tts_error"


class VoiceNotFoundError(TTSServiceError):
    code = "voice_not_found"
