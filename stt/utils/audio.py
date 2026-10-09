from collections.abc import Iterable, Iterator

import numpy as np

from engines.models import AudioChunk, AudioFormatSpec
from exceptions import InvalidAudioFormatError


def calculate_duration(chunks: list[AudioChunk]) -> float:
    if not chunks:
        return 0.0
    total_bytes = sum(len(c.data) for c in chunks)
    bytes_per_second = (
        chunks[0].sample_rate * chunks[0].channels * chunks[0].sample_width
    )
    return total_bytes / bytes_per_second


def convert_chunks(
    chunks: Iterable[AudioChunk], target: AudioFormatSpec | None
) -> Iterator[AudioChunk]:
    """
    Resample/remix/requantize each chunk to `target` format, so a client
    doesn't have to know what format the active provider needs. A no-op
    passthrough if `target` is None (provider accepts anything as-is) or
    a chunk already matches.
    """
    for chunk in chunks:
        if target is None:
            yield chunk
        else:
            yield _convert_chunk(chunk, target)


def _convert_chunk(chunk: AudioChunk, target: AudioFormatSpec) -> AudioChunk:
    if (
        chunk.sample_rate == target.sample_rate
        and chunk.channels == target.channels
        and chunk.sample_width == target.sample_width
    ):
        return chunk

    samples = _to_int16(chunk.data, chunk.sample_width)

    if chunk.channels != target.channels:
        if target.channels != 1:
            raise InvalidAudioFormatError(
                f"Cannot convert {chunk.channels}-channel audio to "
                f"{target.channels} channels"
            )
        samples = samples.reshape(-1, chunk.channels).mean(axis=1).astype(np.int16)

    if chunk.sample_rate != target.sample_rate:
        samples = _resample(samples, chunk.sample_rate, target.sample_rate)

    return AudioChunk(
        data=_from_int16(samples, target.sample_width),
        sample_rate=target.sample_rate,
        channels=target.channels,
        sample_width=target.sample_width,
    )


def _to_int16(data: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 2:
        return np.frombuffer(data, dtype=np.int16)
    if sample_width == 1:
        # 8-bit WAV PCM is unsigned, centered at 128.
        unsigned = np.frombuffer(data, dtype=np.uint8).astype(np.int16)
        return (unsigned - 128) * 256
    if sample_width == 4:
        return (np.frombuffer(data, dtype=np.int32) >> 16).astype(np.int16)
    raise InvalidAudioFormatError(f"Unsupported sample width: {sample_width} bytes")


def _from_int16(samples: np.ndarray, sample_width: int) -> bytes:
    if sample_width == 2:
        return samples.astype(np.int16).tobytes()
    if sample_width == 1:
        unsigned = (samples.astype(np.int32) // 256 + 128).clip(0, 255)
        return unsigned.astype(np.uint8).tobytes()
    if sample_width == 4:
        return (samples.astype(np.int32) << 16).tobytes()
    raise InvalidAudioFormatError(f"Unsupported sample width: {sample_width} bytes")


def _resample(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate or len(samples) == 0:
        return samples

    # Dependency-free linear-interpolation resample - adequate for
    # speech, avoids pulling in scipy/resampy/soxr for this one call.
    duration = len(samples) / from_rate
    old_times = np.linspace(0, duration, num=len(samples), endpoint=False)
    new_len = max(1, round(duration * to_rate))
    new_times = np.linspace(0, duration, num=new_len, endpoint=False)
    resampled = np.interp(new_times, old_times, samples.astype(np.float32))
    return resampled.astype(np.int16)
