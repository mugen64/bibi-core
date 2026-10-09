from engines.models import AudioChunk
from utils.audio import calculate_duration


def test_empty_list_is_zero_duration():
    assert calculate_duration([]) == 0.0


def test_one_second_of_16khz_mono_16bit():
    # 16000 samples/sec * 1 channel * 2 bytes/sample = 32000 bytes/sec
    chunk = AudioChunk(
        data=b"\x00\x00" * 16000, sample_rate=16000, channels=1, sample_width=2
    )
    assert calculate_duration([chunk]) == 1.0


def test_sums_across_multiple_chunks():
    chunk = AudioChunk(
        data=b"\x00\x00" * 8000, sample_rate=16000, channels=1, sample_width=2
    )
    assert calculate_duration([chunk, chunk]) == 1.0
