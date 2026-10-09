import threading
import time

from engines.models import AudioChunk
from engines.whispercpp_engine import WhisperCppEngine


class _FakeModel:
    """Stands in for pywhispercpp's Model - records how many threads
    were inside transcribe() at once, without needing a real whisper
    model file."""

    def __init__(self):
        self.max_concurrent = 0
        self._concurrent = 0
        self._bookkeeping_lock = threading.Lock()

    def transcribe(self, samples, **kwargs):
        with self._bookkeeping_lock:
            self._concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self._concurrent)
        time.sleep(0.05)  # long enough that overlapping calls would reliably collide
        with self._bookkeeping_lock:
            self._concurrent -= 1
        return []


def _make_engine() -> WhisperCppEngine:
    # Bypass __init__ (which loads a real whisper.cpp model) - we only
    # need to exercise the locking behavior around the native call.
    engine = WhisperCppEngine.__new__(WhisperCppEngine)
    engine._model = _FakeModel()
    engine._model_lock = threading.Lock()
    return engine


def _one_chunk() -> list[AudioChunk]:
    return [
        AudioChunk(
            data=b"\x00\x00" * 1600, sample_rate=16000, channels=1, sample_width=2
        )
    ]


def test_concurrent_transcribe_calls_are_serialized():
    # Regression test for a real crash: whisper.cpp's native context
    # isn't safe for concurrent whisper_full() calls, but EngineManager
    # can hand the same cached engine instance to multiple concurrent
    # callers. Without the lock in transcribe(), this test's threads
    # would observe max_concurrent > 1.
    engine = _make_engine()

    threads = [
        threading.Thread(target=engine.transcribe, args=(_one_chunk(),))
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert engine._model.max_concurrent == 1
