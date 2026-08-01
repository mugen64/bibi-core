import os
import numpy as np
from collections.abc import Iterable
from pathlib import Path

from engines.base import STTEngine
from engines.models import Transcript,AudioChunk,TranscriptSegment
from pywhispercpp.model import Model



class WhisperCppEngine(STTEngine):
    def __init__(
        self, 
        model_path: str,
        n_threads: int = os.cpu_count(),
    ):
        self._model_path = model_path
        self._model = Model(
            model=model_path,
            print_progress=False,
            print_realtime=False,
            n_threads=n_threads
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
            raise ValueError(
                "Audio source produced no data"
            )


        return self._pcm_to_float32(
            pcm
        )


    def _validate_chunk(
        self,
        chunk,
        sample_rate,
        channels,
        sample_width,
    ):

        if chunk.sample_rate != sample_rate:
            raise ValueError(
                "All audio chunks must have the same sample rate"
            )

        if chunk.channels != channels:
            raise ValueError(
                "All audio chunks must have the same channel count"
            )

        if chunk.sample_width != sample_width:
            raise ValueError(
                "All audio chunks must have the same sample width"
            )


        # if chunk.sample_rate != 16000:
        #    raise ValueError(
        #        "Whisper requires 16000Hz audio"
        #    )

        if chunk.channels != 1:
            raise ValueError(
                "Whisper requires mono audio"
            )

        if chunk.sample_width != 2:
            raise ValueError(
                "Whisper requires 16-bit PCM"
            )


    def _pcm_to_float32(
        self,
        pcm: bytes,
    ) -> np.ndarray:

        audio = np.frombuffer(
            pcm,
            dtype=np.int16,
        )

        return audio.astype(
            np.float32
        ) / 32768.0

