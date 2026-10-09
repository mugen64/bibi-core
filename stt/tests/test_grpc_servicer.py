import pytest

import engine_manager as engine_manager_module
import stt_pb2
from engines.mock_engine import MockSTTEngine
from grpc_servicer import SpeechToTextServicer


class FakeContext:
    def cancelled(self):
        return False


@pytest.fixture
def servicer(monkeypatch):
    monkeypatch.setattr(
        engine_manager_module.engine_manager, "_engine_cls", MockSTTEngine
    )
    engine_manager_module.engine_manager._engines.clear()
    engine_manager_module.engine_manager._ref_counts.clear()
    return SpeechToTextServicer()


async def _one_chunk(*, seconds: float, end_of_utterance: bool):
    yield stt_pb2.AudioChunkMsg(
        data=b"\x00\x00" * int(16000 * seconds),
        sample_rate=16000,
        channels=1,
        sample_width=2,
        end_of_utterance=end_of_utterance,
    )


async def test_stream_transcribe_yields_a_final_transcript_on_end_of_utterance(
    servicer,
):
    request_iterator = _one_chunk(seconds=1, end_of_utterance=True)
    events = [
        event
        async for event in servicer.StreamTranscribe(request_iterator, FakeContext())
    ]

    assert len(events) == 1
    assert events[0].type == stt_pb2.TranscriptEvent.FINAL
    assert "mock transcript" in events[0].segments[0].text


async def test_health_check_reports_healthy(servicer):
    response = await servicer.HealthCheck(stt_pb2.HealthRequest(), FakeContext())
    assert response.healthy is True
    assert response.model_loaded == engine_manager_module.engine_manager.default_model
