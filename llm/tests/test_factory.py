import pytest

from engines.factory import get_provider_class
from engines.mock_engine import MockEngine
from engines.ollama_engine import OllamaEngine


def test_resolves_known_providers():
    assert get_provider_class("ollama") is OllamaEngine
    assert get_provider_class("mock") is MockEngine


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="nonexistent"):
        get_provider_class("nonexistent")
