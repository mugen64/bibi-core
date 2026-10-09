from output.interface import AudioSink


class BufferSink(AudioSink):
    def __init__(self):
        self.buffer = bytearray()

    async def write(self, chunks):
        async for chunk in chunks:
            self.buffer.extend(chunk.data)

    def getvalue(self) -> bytes:
        return bytes(self.buffer)
