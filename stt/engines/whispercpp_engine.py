import os
from pathlib import Path

import numpy as np
from pywhispercpp.model import Model

from engines.base import AudioSource, STTEngine
from engines.models import AudioFormatSpec, Transcript, TranscriptSegment
from exceptions import InvalidAudioFormatError, ModelNotFoundError

_REQUIRED_FORMAT = AudioFormatSpec(sample_rate=16000, channels=1, sample_width=2)


class WhisperCppEngine(STTEngine):
    @classmethod
    def list_available(cls, directory: Path) -> list[str]:
        return sorted(f.stem for f in directory.glob("*.bin"))

    @classmethod
    def resolve_path(cls, directory: Path, name: str) -> Path:
        model_path = directory / f"{name}.bin"
        if not model_path.is_file():
            raise ModelNotFoundError(name)
        return model_path

    @classmethod
    def required_format(cls) -> AudioFormatSpec:
        return _REQUIRED_FORMAT

    def __init__(
        self,
        model_path: str,
        n_threads: int = os.cpu_count() or 1,
    ):
        self._model_path = model_path
        self._model = Model(
            model=model_path,
            print_progress=False,
            print_realtime=False,
            n_threads=n_threads,
        )

    def transcribe(
        self,
        source: AudioSource,
    ) -> Transcript:

        samples = self._convert_audio(source)

        segments = self._model.transcribe(
            samples,
            print_progress=False,
            print_realtime=False,
        )

        return Transcript(
            # language=self.language,
            segments=[
                TranscriptSegment(
                    start_ms=int(segment.t0 * 10),
                    end_ms=int(segment.t1 * 10),
                    text=segment.text,
                    score=getattr(
                        segment,
                        "probability",
                        None,
                    ),
                )
                for segment in segments
            ],
        )

    def _convert_audio(
        self,
        source: AudioSource,
    ) -> np.ndarray:

        pcm = bytearray()

        sample_rate = None
        channels = None
        sample_width = None

        for chunk in source:
            if sample_rate is None:
                sample_rate = chunk.sample_rate
                channels = chunk.channels
                sample_width = chunk.sample_width

            self._validate_chunk(
                chunk,
                sample_rate,
                channels,
                sample_width,
            )

            pcm.extend(chunk.data)

        if not pcm:
            raise InvalidAudioFormatError("Audio source produced no data")

        return self._pcm_to_float32(pcm)

    def _validate_chunk(
        self,
        chunk,
        sample_rate,
        channels,
        sample_width,
    ):

        if chunk.sample_rate != sample_rate:
            raise InvalidAudioFormatError(
                "All audio chunks must have the same sample rate"
            )

        if chunk.channels != channels:
            raise InvalidAudioFormatError(
                "All audio chunks must have the same channel count"
            )

        if chunk.sample_width != sample_width:
            raise InvalidAudioFormatError(
                "All audio chunks must have the same sample width"
            )

        if chunk.sample_rate != 16000:
            raise InvalidAudioFormatError("Whisper requires 16000Hz audio")

        if chunk.channels != 1:
            raise InvalidAudioFormatError("Whisper requires mono audio")

        if chunk.sample_width != 2:
            raise InvalidAudioFormatError("Whisper requires 16-bit PCM")

    def _pcm_to_float32(
        self,
        pcm: bytes,
    ) -> np.ndarray:

        audio = np.frombuffer(
            pcm,
            dtype=np.int16,
        )

        return audio.astype(np.float32) / 32768.0
