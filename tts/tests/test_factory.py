import pytest

from engines.factory import get_provider_class
from engines.mock_engine import MockEngine
from engines.piper_engine import PiperEngine


def test_resolves_known_providers():
    assert get_provider_class("piper") is PiperEngine
    assert get_provider_class("mock") is MockEngine


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="nonexistent"):
        get_provider_class("nonexistent")
