from engines.models import AudioChunk
from output.buffer import BufferSink


async def _achunks(*pieces: bytes):
    for p in pieces:
        yield AudioChunk(data=p, sample_rate=16000, channels=1, sample_width=2)


async def test_buffer_sink_accumulates_an_async_iterable():
    sink = BufferSink()
    await sink.write(_achunks(b"ab", b"cd", b"ef"))
    assert sink.getvalue() == b"abcdef"


async def test_buffer_sink_starts_empty():
    sink = BufferSink()
    assert sink.getvalue() == b""
