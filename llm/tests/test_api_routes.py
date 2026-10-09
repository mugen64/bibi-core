import json

import pytest
from fastapi.testclient import TestClient

import engine_manager as engine_manager_module
from engines.mock_engine import MockEngine
from server import get_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(engine_manager_module.engine_manager, "engine", MockEngine())
    return TestClient(get_app())


def test_health_reports_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "ollama_reachable": True}


def test_chat_returns_the_mock_echo(client):
    resp = client.post("/chat", json={"prompt": "hello"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    chunk_text = "".join(d["text"] for d in data if d["type"] == "chunk")
    assert chunk_text.strip() == "You said: hello"
    assert data[-1] == {"type": "done"}


def test_chat_rejects_an_empty_prompt(client):
    resp = client.post("/chat", json={"prompt": "   "})
    assert resp.status_code == 400


def test_chat_stream_returns_ndjson_ending_in_done(client):
    resp = client.post("/chat/stream", json={"prompt": "hello"})
    assert resp.status_code == 200

    lines = [json.loads(line) for line in resp.text.strip().split("\n") if line]
    assert lines[-1] == {"type": "done"}
    chunk_text = "".join(line["text"] for line in lines if line["type"] == "chunk")
    assert chunk_text.strip() == "You said: hello"
