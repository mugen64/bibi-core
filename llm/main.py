from config import MODEL_DIR, DEFAULT_MODEL
from engine_manager import STTManager
from engines.audio_sources import WavFileAudioSource

sm = STTManager()

def main():
    e = sm.get_engine("ggml-base")
    src = WavFileAudioSource("../tts/test.wav")

    t = e.transcribe(src)

    print([s.text for s in t.segments])


if __name__ == "__main__":
    main()
