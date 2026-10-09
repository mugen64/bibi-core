import pytest
from fastapi.testclient import TestClient

import engine_manager as engine_manager_module
from engines.mock_engine import MockEngine
from server import get_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(engine_manager_module.engine_manager, "_engine_cls", MockEngine)
    engine_manager_module.engine_manager._engines.clear()
    engine_manager_module.engine_manager._ref_counts.clear()
    return TestClient(get_app())


def test_list_voices_returns_the_mock_provider(client):
    resp = client.get("/voices")
    assert resp.status_code == 200
    assert resp.json()["data"] == ["mock"]


def test_tts_returns_a_wav_file(client):
    resp = client.post("/tts", json={"text": "hello", "voice": "mock", "format": "wav"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert len(resp.content) > 44  # bigger than just a WAV header


def test_tts_rejects_an_unsupported_format(client):
    resp = client.post("/tts", json={"text": "hello", "voice": "mock", "format": "mp3"})
    assert resp.status_code == 422  # pydantic rejects the bad enum value


def test_tts_stream_sends_back_audio_bytes(client):
    with client.websocket_connect("/tts-stream") as ws:
        ws.send_json({"text": "hello", "voice": "mock"})
        data = ws.receive_bytes()
        assert len(data) > 0
