import config as config_module
from engine_manager import EngineManager


def test_uses_the_configured_provider(monkeypatch):
    monkeypatch.setattr(config_module.config.engine, "provider", "mock")
    manager = EngineManager()
    assert type(manager.engine).__name__ == "MockEngine"


async def test_stream_chat_response_yields_the_mock_echo(monkeypatch):
    monkeypatch.setattr(config_module.config.engine, "provider", "mock")
    manager = EngineManager()
    await manager.ensure_ready()  # mock provider is always ready

    chunks = [chunk async for chunk in manager.stream_chat_response("hello")]
    assert "".join(chunks).strip() == "You said: hello"


async def test_health_check_delegates_to_the_engine(monkeypatch):
    monkeypatch.setattr(config_module.config.engine, "provider", "mock")
    manager = EngineManager()
    assert await manager.health_check() is True
