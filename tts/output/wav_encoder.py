import wave
from io import BytesIO


class WavEncoder:

    def encode(self, chunks) -> BytesIO:
        buffer = BytesIO()

        chunks = iter(chunks)
        first = next(chunks)

        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(first.channels)
            wav.setsampwidth(first.sample_width)
            wav.setframerate(first.sample_rate)

            wav.writeframes(first.data)

            for chunk in chunks:
                wav.writeframes(chunk.data)

        buffer.seek(0)

        return buffer

