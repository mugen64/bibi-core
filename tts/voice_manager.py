from pathlib import Path
from config import VOICE_DIR, DEFAULT_VOICE


class VoiceManager:
    def __init__(self):
        self.voice_dir = VOICE_DIR
        self.default_voice = DEFAULT_VOICE

    def list_voices(self):
        """
        Return all voices that have both .onnx and .json files.
        """
        voices = []

        for model in self.voice_dir.glob("*.onnx"):
            config_file = Path(str(model) + ".json")

            if config_file.exists():
                voices.append(model.name)

        return voices

    def get_voice_path(self, voice_name=None):
        """
        Return the full path to a voice model.
        """
        if voice_name is None:
            voice_name = self.default_voice

        voice_path = self.voice_dir / voice_name

        if not voice_path.exists():
            raise FileNotFoundError(
                f"Voice not found: {voice_path}"
            )

        json_path = Path(str(voice_path) + ".json")

        if not json_path.exists():
            raise FileNotFoundError(
                f"Missing voice config: {json_path}"
            )

        return voice_path

