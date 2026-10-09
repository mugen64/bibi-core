import pytest

import engine_manager as engine_manager_module
import tts_pb2
from engines.mock_engine import MockEngine
from grpc_servicer import TextToSpeechServicer


class FakeContext:
    def cancelled(self):
        return False

    async def abort(self, code, details):
        raise AssertionError(f"unexpected abort: {code} {details}")


@pytest.fixture
def servicer(monkeypatch):
    monkeypatch.setattr(engine_manager_module.engine_manager, "_engine_cls", MockEngine)
    engine_manager_module.engine_manager._engines.clear()
    engine_manager_module.engine_manager._ref_counts.clear()
    return TextToSpeechServicer()


async def test_stream_synthesize_yields_audio_chunks(servicer):
    request = tts_pb2.SynthesizeRequest(text="hello", voice="mock")
    chunks = [c async for c in servicer.StreamSynthesize(request, FakeContext())]

    assert len(chunks) >= 1
    assert all(c.sample_rate == 22050 and len(c.data) > 0 for c in chunks)


async def test_health_check_reports_healthy(servicer):
    response = await servicer.HealthCheck(tts_pb2.HealthRequest(), FakeContext())
    assert response.healthy is True
    assert "mock" in response.voices_available
