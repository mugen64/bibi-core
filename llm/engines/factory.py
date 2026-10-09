"""
Maps a config-selected provider name to an LLMEngine implementation.
EngineManager depends only on this + the LLMEngine ABC - never a
concrete engine class - so adding a new backend means writing one
class and registering it here.
"""

from engines.base import LLMEngine
from engines.mock_engine import MockEngine
from engines.ollama_engine import OllamaEngine

_PROVIDERS: dict[str, type[LLMEngine]] = {
    "ollama": OllamaEngine,
    "mock": MockEngine,
}


def get_provider_class(provider: str) -> type[LLMEngine]:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. Available: {sorted(_PROVIDERS)}"
        ) from None
