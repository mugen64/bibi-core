from collections import OrderedDict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from config import config
from engines.base import STTEngine
from engines.factory import get_provider_class
from engines.models import AudioChunk
from exceptions import ModelNotFoundError
from utils.audio import convert_chunks


class EngineManager:
    def __init__(self, max_loaded_models: int = config.models.max_loaded):
        self._model_dir: Path = config.models.directory
        self._default_model = config.models.default
        self._engine_cls = get_provider_class(config.engine.provider)
        self.max_loaded_models = max_loaded_models

        self._engines: OrderedDict[str, STTEngine] = OrderedDict()
        self._ref_counts: dict[str, int] = {}
        # Guards all dicts above - get_engine/acquire_engine can be called
        # concurrently from multiple request-handling threads (sync HTTP
        # routes run in FastAPI's thread pool) or coroutines (grpc
        # servicer), so mutations need to be atomic.
        self._lock = Lock()

    def list_models(self) -> list[str]:
        return self._engine_cls.list_available(self._model_dir)

    def prepare_audio(self, chunks: Iterable[AudioChunk]) -> Iterator[AudioChunk]:
        """
        Convert incoming audio to whatever format the active provider
        requires, so callers never need to know that themselves. A
        no-op passthrough for a provider that accepts any format.
        """
        return convert_chunks(chunks, self._engine_cls.required_format())

    @property
    def default_model(self) -> str:
        return self._default_model

    @contextmanager
    def acquire_engine(self, model: str | None = None):
        """
        Preferred way to use an engine. Increments a ref count while the
        `with` block is active, so eviction can never remove an engine
        that's mid-use by this or any other concurrent request.

        Usage:
            with engine_manager.acquire_engine(model) as engine:
                engine.transcribe(audio)
        """
        model = model or self._default_model
        engine = self._get_or_load(model)

        with self._lock:
            self._ref_counts[model] = self._ref_counts.get(model, 0) + 1

        try:
            yield engine
        finally:
            with self._lock:
                self._ref_counts[model] -= 1
                if self._ref_counts[model] <= 0:
                    del self._ref_counts[model]
                # A slot may have freed up - try evicting now that this
                # request is done, in case capacity was exceeded while
                # this engine was pinned in use.
                self._evict_if_over_capacity()

    def get_engine(self, model: str | None = None) -> STTEngine:
        """
        Unsafe relative to eviction races - kept for simple callers that
        do one quick synchronous call and return immediately. Prefer
        acquire_engine() for anything long-running or concurrent.
        """
        return self._get_or_load(model or self._default_model)

    def _get_or_load(self, model: str) -> STTEngine:
        if Path(model).name != model:
            raise ModelNotFoundError(model)

        with self._lock:
            if model in self._engines:
                self._engines.move_to_end(model)
                return self._engines[model]

        # Resolve + load outside the lock - model loading is slow (I/O +
        # compute), no need to hold the lock and block other callers
        # (even ones asking for an already-cached, different model)
        # during it.
        model_path = self._engine_cls.resolve_path(self._model_dir, model)
        engine = self._engine_cls(model_path)

        with self._lock:
            # Another thread may have loaded the same model while we
            # were loading ours - keep whichever landed first, discard
            # the duplicate rather than overwriting (avoids a subtle bug
            # where an in-flight acquire_engine() caller holds a
            # reference to the discarded instance).
            if model not in self._engines:
                self._engines[model] = engine
            self._engines.move_to_end(model)
            # Protect `model` itself - without this, a fresh entry with
            # no active ref count yet (the common case: get_engine()
            # never increments one) could get evicted by its own
            # insertion's capacity sweep if an older entry is pinned
            # in-use, and we'd return a KeyError below.
            self._evict_if_over_capacity(protect=model)
            return self._engines[model]

    def _evict_if_over_capacity(self, protect: str | None = None) -> None:
        """Must be called with self._lock held."""
        if len(self._engines) <= self.max_loaded_models:
            return

        # Walk oldest -> newest, evict the first entries with no active
        # references. If every loaded model is currently in use, we
        # simply stay over capacity until one is released - correctness
        # over strict capacity enforcement.
        for model in list(self._engines.keys()):
            if len(self._engines) <= self.max_loaded_models:
                return
            if model == protect:
                continue
            if self._ref_counts.get(model, 0) > 0:
                continue  # in use, skip
            del self._engines[model]

    def loaded_models(self) -> list[str]:
        with self._lock:
            return list(self._engines.keys())


# Singleton - created once at import time, shared by every module that
# imports `engine_manager` from here (api routes, grpc servicer, etc.).
# Whisper models get loaded lazily via get_engine()/acquire_engine() and
# cached in self._engines (up to max_loaded_models, LRU-evicted), so the
# first call per model pays the load cost and every subsequent call
# reuses the already-loaded model in memory.
engine_manager = EngineManager()
