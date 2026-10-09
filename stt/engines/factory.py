"""
Maps a config-selected provider name to an STTEngine implementation.
EngineManager depends only on this + the STTEngine ABC - never a
concrete engine class - so adding a new backend means writing one
class and registering it here.
"""

from engines.base import STTEngine
from engines.mock_engine import MockSTTEngine
from engines.whispercpp_engine import WhisperCppEngine

_PROVIDERS: dict[str, type[STTEngine]] = {
    "whispercpp": WhisperCppEngine,
    "mock": MockSTTEngine,
}


def get_provider_class(provider: str) -> type[STTEngine]:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown STT provider '{provider}'. Available: {sorted(_PROVIDERS)}"
        ) from None
