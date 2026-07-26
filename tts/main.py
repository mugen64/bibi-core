import wave
from piper_engine import Piper
from voice_manager import VoiceManager
from play_stream import play_stream


manager = VoiceManager()

for voice in manager.list_voices():
    print("-", voice)

voice_path = manager.get_voice_path()
print("using", voice_path)

tts = Piper(voice_path)

tts.speak(
    "Hello, this is my local Piper text to speech system.",
    "test.wav"
)

print("Generated test.wav")


play_stream(tts,"Hello this is streaming")




