import config as config_module
from engine_manager import EngineManager


def _mock_manager(monkeypatch, max_loaded_models: int = 2) -> EngineManager:
    monkeypatch.setattr(config_module.config.engine, "provider", "mock")
    return EngineManager(max_loaded_models=max_loaded_models)


def test_uses_the_configured_provider(monkeypatch):
    manager = _mock_manager(monkeypatch)
    assert type(manager.get_engine("a")).__name__ == "MockSTTEngine"


def test_repeated_get_engine_returns_the_cached_instance(monkeypatch):
    manager = _mock_manager(monkeypatch)
    first = manager.get_engine("a")
    second = manager.get_engine("a")
    assert first is second


def test_lru_eviction_once_over_capacity(monkeypatch):
    manager = _mock_manager(monkeypatch, max_loaded_models=2)
    a = manager.get_engine("a")
    manager.get_engine("b")
    manager.get_engine("c")  # pushes capacity to 3, should evict "a" (oldest, unused)

    assert "a" not in manager.loaded_models()
    assert set(manager.loaded_models()) == {"b", "c"}
    # "a" wasn't just dropped from the dict - a fresh load gets a new instance
    assert manager.get_engine("a") is not a


def test_acquire_engine_protects_an_in_use_entry_from_eviction(monkeypatch):
    # Regression test: the engine cache used to hold its lock across the
    # entire (slow) model load and had no eviction at all. Now it must
    # never evict something actively held via acquire_engine(), even
    # when loading new models pushes it over max_loaded_models.
    manager = _mock_manager(monkeypatch, max_loaded_models=1)

    with manager.acquire_engine("a") as held:
        manager.get_engine("b")  # over capacity now - "a" must survive, it's in use
        assert "a" in manager.loaded_models()
        assert manager.get_engine("a") is held

    # released - now eviction is free to reclaim it on the next load
    manager.get_engine("c")
    assert "a" not in manager.loaded_models()
