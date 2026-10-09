import io
import wave

import pytest
from fastapi.testclient import TestClient

import engine_manager as engine_manager_module
from engines.mock_engine import MockSTTEngine
from server import get_app


def _wav_bytes(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        engine_manager_module.engine_manager, "_engine_cls", MockSTTEngine
    )
    engine_manager_module.engine_manager._engines.clear()
    engine_manager_module.engine_manager._ref_counts.clear()
    return TestClient(get_app())


def test_list_models_returns_the_mock_provider(client):
    resp = client.get("/models")
    assert resp.status_code == 200
    assert resp.json()["data"] == ["mock"]


def test_transcribe_returns_a_mock_transcript(client):
    resp = client.post(
        "/transcribe",
        files={"file": ("test.wav", _wav_bytes(seconds=1.0), "audio/wav")},
    )
    assert resp.status_code == 200
    segments = resp.json()["data"]["segments"]
    assert "mock transcript" in segments[0]["text"]


def test_transcribe_rejects_a_non_wav_content_type(client):
    resp = client.post(
        "/transcribe",
        files={"file": ("test.txt", b"not audio", "text/plain")},
    )
    assert resp.status_code == 400


def test_transcribe_stream_sends_back_a_transcript(client):
    with client.websocket_connect("/transcribe-stream") as ws:
        five_seconds_of_silence = b"\x00\x00" * (16000 * 5)
        ws.send_bytes(five_seconds_of_silence)
        message = ws.receive_json()
        assert "mock transcript" in message["text"]
