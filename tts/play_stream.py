import subprocess
from engines.piper_engine import Piper
from output.host import HostAudioSink

sink = HostAudioSink()

async def play_stream(piper, text):
    await sink.write(piper.stream(text))
