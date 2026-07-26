import sounddevice as sd
from output.interface import AudioSink

class HostAudioSink(AudioSink):
    async def write(self, chunks):
        stream = None

        for chunk in chunks:
            if stream is None:
                stream = sd.RawOutputStream(
                    samplerate=chunk.sample_rate,
                    channels=chunk.channels,
                    dtype="int16",
                )
                stream.start()

            stream.write(chunk.data)

        if stream:
            stream.stop()
            stream.close()

