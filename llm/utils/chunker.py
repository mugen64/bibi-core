"""
Buffers a raw token stream into sentence/clause-sized chunks suitable
for handing to the TTS service.

This is the piece that makes streaming TTS sound natural instead of
choppy - sending individual tokens to TTS produces bad prosody, so we
wait for a sentence boundary (or a length-based fallback) before
emitting a chunk.
"""

from collections.abc import AsyncIterator

from config import config

# Common abbreviations that end in a period but AREN'T sentence boundaries.
# Not exhaustive - extend as you hit real cases in testing.
_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc."}


def _ends_with_abbreviation(text: str) -> bool:
    last_word = text.strip().split(" ")[-1].lower() if text.strip() else ""
    return last_word in _ABBREVIATIONS


def _is_mid_number(text: str, boundary_char: str) -> bool:
    """Avoid splitting '3.14' or '$5.00' on the decimal point."""
    if boundary_char != ".":
        return False
    idx = text.rfind(".")
    if idx <= 0 or idx >= len(text) - 1:
        return False
    return text[idx - 1].isdigit() and text[idx + 1].isdigit()


async def chunk_stream(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """
    Consumes a raw token stream, yields complete sentence/clause chunks.
    """
    buffer = ""

    async for token in token_stream:
        buffer += token

        stripped = buffer.strip()
        if not stripped:
            continue

        last_char = stripped[-1]
        hit_boundary = last_char in config.chunking.boundary_chars

        if hit_boundary and _is_mid_number(stripped, last_char):
            hit_boundary = False

        if hit_boundary and _ends_with_abbreviation(stripped):
            hit_boundary = False

        long_enough = len(stripped) >= config.chunking.min_chunk_chars
        force_flush = len(stripped) >= config.chunking.max_chunk_chars

        if (hit_boundary and long_enough) or force_flush:
            yield stripped
            buffer = ""

    # Flush whatever's left when the stream ends
    remainder = buffer.strip()
    if remainder:
        yield remainder
