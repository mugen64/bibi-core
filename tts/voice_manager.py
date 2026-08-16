from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from config import config
from engines.piper_engine import Piper


class VoiceManager:
    def __init__(self, max_loaded_voices: int = config.voices.max_loaded):
        self.voice_dir: Path = config.voices.directory
        self.default_voice = config.voices.default
        self.max_loaded_voices = max_loaded_voices

        self._engines: OrderedDict[str, Piper] = OrderedDict()
        self._ref_counts: dict[str, int] = {}
        # Guards all three dicts above - get_engine/acquire/release can
        # be called concurrently from multiple request-handling threads
        # (sync HTTP routes run in FastAPI's thread pool) or coroutines
        # (grpc servicer), so mutations need to be atomic.
        self._lock = Lock()

    def list_voices(self) -> list[str]:
        voices = []
        for model in self.voice_dir.glob("*.onnx"):
            config_file = Path(str(model) + ".json")
            if config_file.exists():
                voices.append(model.name)
        return voices

    def get_voice_path(self, voice_name: str | None = None) -> Path:
        if voice_name is None:
            voice_name = self.default_voice

        voice_path = self.voice_dir / voice_name
        if not voice_path.exists():
            raise FileNotFoundError(f"Voice not found: {voice_path}")

        json_path = Path(str(voice_path) + ".json")
        if not json_path.exists():
            raise FileNotFoundError(f"Missing voice config: {json_path}")

        return voice_path

    @contextmanager
    def acquire_engine(self, voice_name: str | None = None):
        """
        Preferred way to use an engine. Increments a ref count while
        the `with` block is active, so eviction can never remove an
        engine that's mid-use by this or any other concurrent request.

        Usage:
            with voice_manager.acquire_engine(request.voice) as engine:
                for chunk in engine.stream(text):
                    ...
        """
        voice_name = voice_name or self.default_voice
        engine = self._get_or_load(voice_name)

        with self._lock:
            self._ref_counts[voice_name] = self._ref_counts.get(voice_name, 0) + 1

        try:
            yield engine
        finally:
            with self._lock:
                self._ref_counts[voice_name] -= 1
                if self._ref_counts[voice_name] <= 0:
                    del self._ref_counts[voice_name]
                # A slot may have freed up - try evicting now that this
                # request is done, in case capacity was exceeded while
                # this engine was pinned in use.
                self._evict_if_over_capacity()

    def get_engine(self, voice_name: str | None = None) -> Piper:
        """
        Unsafe relative to eviction races - kept for simple callers that
        do one quick synchronous synthesis and return immediately (e.g.
        the existing /tts HTTP route), where the window for a race is
        negligible. Prefer acquire_engine() for anything long-running
        or concurrent, like StreamSynthesize.
        """
        return self._get_or_load(voice_name or self.default_voice)

    def _get_or_load(self, voice_name: str) -> Piper:
        with self._lock:
            if voice_name in self._engines:
                self._engines.move_to_end(voice_name)
                return self._engines[voice_name]

        # Load outside the lock - model loading is slow (I/O + compute),
        # no need to hold the lock and block other callers during it.
        voice_path = self.get_voice_path(voice_name)
        engine = Piper(voice_path)

        with self._lock:
            # Another thread may have loaded the same voice while we
            # were loading ours - keep whichever landed first, discard
            # the duplicate rather than overwriting (avoids a subtle
            # bug where an in-flight acquire_engine() caller holds a
            # reference to the discarded instance).
            if voice_name not in self._engines:
                self._engines[voice_name] = engine
            self._engines.move_to_end(voice_name)
            self._evict_if_over_capacity()
            return self._engines[voice_name]

    def _evict_if_over_capacity(self) -> None:
        """Must be called with self._lock held."""
        if len(self._engines) <= self.max_loaded_voices:
            return

        # Walk oldest -> newest, evict the first entries with no active
        # references. If every loaded voice is currently in use, we
        # simply stay over capacity until one is released - correctness
        # over strict capacity enforcement.
        for voice_name in list(self._engines.keys()):
            if len(self._engines) <= self.max_loaded_voices:
                return
            if self._ref_counts.get(voice_name, 0) > 0:
                continue  # in use, skip
            del self._engines[voice_name]

    def unload(self, voice_name: str) -> None:
        """Explicitly evict a specific voice. No-ops if currently in use."""
        with self._lock:
            if self._ref_counts.get(voice_name, 0) > 0:
                return
            self._engines.pop(voice_name, None)

    def loaded_voices(self) -> list[str]:
        with self._lock:
            return list(self._engines.keys())


voice_manager = VoiceManager()
