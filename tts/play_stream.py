from output.host import HostAudioSink
from utils.async_io import iter_in_thread

sink = HostAudioSink()


async def play_stream(piper, text):
    await sink.write(iter_in_thread(piper.stream, text))
