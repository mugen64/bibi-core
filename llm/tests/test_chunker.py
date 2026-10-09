from utils.chunker import chunk_stream


async def _tokens(*pieces: str) -> list[str]:
    async def gen():
        for p in pieces:
            yield p

    return [chunk async for chunk in chunk_stream(gen())]


async def test_flushes_at_sentence_boundary():
    chunks = await _tokens("Hello there, how are you doing today? ", "Fine.")
    assert chunks[0] == "Hello there, how are you doing today?"


async def test_abbreviation_does_not_trigger_a_flush():
    chunks = await _tokens("I asked Dr. Smith a long enough question.")
    assert len(chunks) == 1
    assert chunks[0] == "I asked Dr. Smith a long enough question."


async def test_decimal_point_does_not_trigger_a_flush():
    chunks = await _tokens("The long enough reading was 3.14 on the gauge.")
    assert len(chunks) == 1
    assert "3.14" in chunks[0]


async def test_short_text_is_not_flushed_at_boundary():
    # "Hi." is below min_chunk_chars (10) - shouldn't flush on the boundary
    # char alone, only once the stream ends (the trailing flush).
    chunks = await _tokens("Hi.")
    assert chunks == ["Hi."]


async def test_force_flushes_past_max_chunk_chars_without_a_boundary():
    # Fed in small pieces so the length check has a chance to trip
    # mid-stream rather than seeing the whole 250 chars in one token.
    long_text = "a" * 250  # no boundary char anywhere, exceeds max_chunk_chars (200)
    pieces = [long_text[i : i + 10] for i in range(0, len(long_text), 10)]
    chunks = await _tokens(*pieces)
    assert len(chunks) == 2
    assert "".join(chunks) == long_text


async def test_flushes_remainder_at_end_of_stream():
    chunks = await _tokens("No terminal punctuation but long enough to flush")
    assert chunks == ["No terminal punctuation but long enough to flush"]


async def test_empty_stream_yields_nothing():
    assert await _tokens() == []
