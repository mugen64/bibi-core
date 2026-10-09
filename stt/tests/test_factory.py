import pytest

from engines.factory import get_provider_class
from engines.mock_engine import MockSTTEngine
from engines.whispercpp_engine import WhisperCppEngine


def test_resolves_known_providers():
    assert get_provider_class("whispercpp") is WhisperCppEngine
    assert get_provider_class("mock") is MockSTTEngine


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="nonexistent"):
        get_provider_class("nonexistent")
