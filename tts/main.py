import asyncio
from engines.piper_engine import Piper
from voice_manager import VoiceManager
from play_stream import play_stream
from output.host import HostAudioSink


vm = VoiceManager()
voice = vm.get_voice_path()
engine = Piper(voice)
asyncio.run(play_stream(engine, "Play a stream daily at 12 pm"))





