import config as config_module
from engine_manager import EngineManager


def _mock_manager(monkeypatch, max_loaded_voices: int = 2) -> EngineManager:
    monkeypatch.setattr(config_module.config.engine, "provider", "mock")
    return EngineManager(max_loaded_voices=max_loaded_voices)


def test_uses_the_configured_provider(monkeypatch):
    manager = _mock_manager(monkeypatch)
    assert type(manager.get_engine("a")).__name__ == "MockEngine"


def test_repeated_get_engine_returns_the_cached_instance(monkeypatch):
    manager = _mock_manager(monkeypatch)
    first = manager.get_engine("a")
    second = manager.get_engine("a")
    assert first is second


def test_lru_eviction_once_over_capacity(monkeypatch):
    manager = _mock_manager(monkeypatch, max_loaded_voices=2)
    a = manager.get_engine("a")
    manager.get_engine("b")
    manager.get_engine("c")  # pushes capacity to 3, should evict "a" (oldest, unused)

    assert "a" not in manager.loaded_voices()
    assert set(manager.loaded_voices()) == {"b", "c"}
    assert manager.get_engine("a") is not a


def test_acquire_engine_protects_an_in_use_entry_from_eviction(monkeypatch):
    # Regression test: the just-loaded entry used to be evictable by its
    # own insertion's capacity sweep when an older entry was pinned
    # in-use, raising a KeyError instead of returning the new engine.
    manager = _mock_manager(monkeypatch, max_loaded_voices=1)

    with manager.acquire_engine("a") as held:
        manager.get_engine("b")  # over capacity now - "a" must survive, it's in use
        assert "a" in manager.loaded_voices()
        assert manager.get_engine("a") is held

    manager.get_engine("c")
    assert "a" not in manager.loaded_voices()


async def test_aacquire_engine_is_async_safe(monkeypatch):
    manager = _mock_manager(monkeypatch)
    async with manager.aacquire_engine("a") as engine:
        assert type(engine).__name__ == "MockEngine"
    assert "a" in manager.loaded_voices()
