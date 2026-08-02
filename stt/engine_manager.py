from pathlib import Path
from config import MODEL_DIR, DEFAULT_MODEL
from engines.base import STTEngine
from engines.whispercpp_engine import WhisperCppEngine


class STTManager:
    def __init__(self):
        self._model_dir = MODEL_DIR
        self._engines: dict[str, STTEngine] = {}
        self._default_model = DEFAULT_MODEL

    def list_models(self) -> list[str]:
        """
        Returns all available whisper models 
        """
        models = []
        for file in self._model_dir.glob("*.bin"):
            models.append(file.stem)

        return sorted(models)

    def has_model(self, model:str)->bool:

        return self._model_dir/f"{model}.bin".exists()

    def get_engine(self, model: str | None = None)->STTEngine:

        if model is None:
            model = self._default_model
            
        if model in self._engines:
            return self._engines[model]

        model_path =  self._model_dir/f"{model}.bin"

        if not model_path.exists():
             raise FileNotFoundError(
                f"Unknown model '{model}'"
            )

        engine = WhisperCppEngine(model_path)
        self._engines[model]= engine
        
        return engine

# Singleton - created once at import time, shared by every module that
# imports `stt_manager` from here (api routes, grpc servicer, etc.).
# Whisper models get loaded lazily via get_engine() and cached in
# self._engines, so the first call per model pays the load cost and
# every subsequent call reuses the already-loaded model in memory.
stt_manager = STTManager()
