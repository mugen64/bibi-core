from engines.models import AudioChunk


def calculate_duration(chunks: list[AudioChunk]) -> float:
    if not chunks:
        return 0.0
    total_bytes = sum(len(c.data) for c in chunks)
    bytes_per_second = (
        chunks[0].sample_rate * chunks[0].channels * chunks[0].sample_width
    )
    return total_bytes / bytes_per_second
