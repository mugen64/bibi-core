import asyncio

from output.interface import AudioSink


class HttpAudioSink(AudioSink):

    def __init__(self, websocket):
        self.websocket = websocket

    async def write(self, chunks):
        async for chunk in chunks:
            await self.websocket.send_bytes(
                chunk.data
            )

