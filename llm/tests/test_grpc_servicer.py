import pytest

import engine_manager as engine_manager_module
import llm_pb2
from engines.mock_engine import MockEngine
from grpc_servicer import LLMChatServicer


class FakeContext:
    def __init__(self):
        self.aborted = None

    def cancelled(self):
        return False

    async def abort(self, code, details):
        self.aborted = (code, details)


@pytest.fixture
def servicer(monkeypatch):
    monkeypatch.setattr(engine_manager_module.engine_manager, "engine", MockEngine())
    return LLMChatServicer()


async def test_stream_chat_yields_chunks_then_done(servicer):
    request = llm_pb2.ChatRequest(prompt="hello")
    context = FakeContext()

    events = [event async for event in servicer.StreamChat(request, context)]

    assert events[-1].type == llm_pb2.ChatEvent.DONE
    text = "".join(e.text for e in events if e.type == llm_pb2.ChatEvent.CHUNK)
    assert text.strip() == "You said: hello"
    assert context.aborted is None


async def test_health_check_reports_healthy(servicer):
    response = await servicer.HealthCheck(llm_pb2.HealthRequest(), FakeContext())
    assert response.healthy is True
    assert response.ollama_reachable is True
