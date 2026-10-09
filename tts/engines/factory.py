"""
Maps a config-selected provider name to a TTSEngine implementation.
EngineManager depends only on this + the TTSEngine ABC - never a
concrete engine class - so adding a new backend means writing one
class and registering it here.
"""

from engines.base import TTSEngine
from engines.mock_engine import MockEngine
from engines.piper_engine import PiperEngine

_PROVIDERS: dict[str, type[TTSEngine]] = {
    "piper": PiperEngine,
    "mock": MockEngine,
}


def get_provider_class(provider: str) -> type[TTSEngine]:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown TTS provider '{provider}'. Available: {sorted(_PROVIDERS)}"
        ) from None
