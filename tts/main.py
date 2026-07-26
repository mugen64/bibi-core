import wave
from engines.piper_engine import Piper
from voice_manager import VoiceManager
# from play_stream import play_stream
from output.host import HostAudioSink


manager = VoiceManager()

for voice in manager.list_voices():
    print("-", voice)

voice_path = manager.get_voice_path()
print("using", voice_path)

tts = Piper(voice_path)

host = HostAudioSink()

audio = tts.stream("Hello World")

host.write(audio)





