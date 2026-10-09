import numpy as np
import pytest

from engines.models import AudioChunk, AudioFormatSpec
from exceptions import InvalidAudioFormatError
from utils.audio import convert_chunks

TARGET = AudioFormatSpec(sample_rate=16000, channels=1, sample_width=2)


def _tone(seconds: float, rate: int, channels: int) -> AudioChunk:
    n = int(seconds * rate)
    t = np.linspace(0, seconds, n, endpoint=False)
    mono = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    samples = np.column_stack([mono] * channels).flatten() if channels > 1 else mono
    return AudioChunk(
        data=samples.tobytes(), sample_rate=rate, channels=channels, sample_width=2
    )


def test_passthrough_when_target_is_none():
    chunk = _tone(0.1, 44100, 2)
    (out,) = list(convert_chunks([chunk], None))
    assert out is chunk


def test_passthrough_when_already_matching():
    chunk = _tone(0.1, 16000, 1)
    (out,) = list(convert_chunks([chunk], TARGET))
    assert out is chunk


def test_resamples_to_target_rate():
    chunk = _tone(1.0, 44100, 1)
    (out,) = list(convert_chunks([chunk], TARGET))
    assert out.sample_rate == 16000
    n_samples = len(out.data) // out.sample_width
    assert n_samples == pytest.approx(16000, abs=2)


def test_downmixes_stereo_to_mono():
    chunk = _tone(0.5, 16000, 2)
    (out,) = list(convert_chunks([chunk], TARGET))
    assert out.channels == 1
    n_samples = len(out.data) // out.sample_width
    assert n_samples == 8000


def test_rescales_8bit_to_16bit():
    chunk = AudioChunk(
        data=bytes([128, 0, 255]), sample_rate=16000, channels=1, sample_width=1
    )
    (out,) = list(convert_chunks([chunk], TARGET))
    assert out.sample_width == 2
    samples = np.frombuffer(out.data, dtype=np.int16)
    assert samples[0] == 0  # midpoint (128) -> silence
    assert samples[1] < 0  # 0 -> most negative
    assert samples[2] > 0  # 255 -> most positive


def test_unsupported_sample_width_raises():
    chunk = AudioChunk(
        data=b"\x00\x00\x00", sample_rate=16000, channels=1, sample_width=3
    )
    with pytest.raises(InvalidAudioFormatError):
        list(convert_chunks([chunk], TARGET))
