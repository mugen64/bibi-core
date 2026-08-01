import wave
from pathlib import Path
from engines.models import AudioChunk
from engines.base import AudioSource
from fastapi import WebSocket


class WavFileAudioSource(AudioSource):
    def __init__(self, path: Path):
        self.path = path
    def __iter__(self):
        with wave.open(str(self.path), "rb") as wav:
            while True:
                data = wav.readframes(4096)
                if not data:
                    break
                yield AudioChunk(
                    data=data,
                    sample_rate=wav.getframerate(),
                    channels=wav.getnchannels(),
                    sample_width=wav.getsampwidth(),
                )



class WebSocketAudioSource:

    def __init__(
        self,
        websocket: WebSocket,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
    ):
        self.websocket = websocket
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width


    async def receive_chunk(
        self,
    ) -> AudioChunk | None:

        try:

            data = await (
                self.websocket.receive_bytes()
            )


            return AudioChunk(
                data=data,
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=self.sample_width,
            )


        except Exception:

            return None
