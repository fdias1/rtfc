"""Serviço de diarização do processo: um extrator de embeddings, carregado sob demanda.

Roda numa thread própria (não disputa a thread do Whisper). Se o modelo não puder ser
baixado (sem rede) a diarização fica desligada e a transcrição segue sem falantes.
"""

import asyncio
import contextlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import numpy as np

from rtfc.diarization.clustering import Vector
from rtfc.diarization.models import download_embedding

log = logging.getLogger(__name__)

RATE = 16_000


class SpeakerEmbedder(Protocol):
    def embed(self, audio: Vector) -> Vector | None: ...


class SherpaEmbedder:
    def __init__(self) -> None:
        import sherpa_onnx

        path = download_embedding()
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(path), num_threads=2)
        )

    def embed(self, audio: Vector) -> Vector | None:
        if len(audio) < RATE // 4:
            return None
        stream = self._extractor.create_stream()
        stream.accept_waveform(RATE, audio)
        stream.input_finished()
        if not self._extractor.is_ready(stream):
            return None
        return np.asarray(self._extractor.compute(stream), dtype=np.float32)


class FakeEmbedder:
    """Para os testes E2E (`RTFC_DIARIZER=fake`): alterna entre dois falantes."""

    def __init__(self) -> None:
        self._n = 0

    def embed(self, audio: Vector) -> Vector | None:
        v = np.zeros(4, dtype=np.float32)
        v[self._n % 2] = 1.0
        self._n += 1
        return v


class DiarizationService:
    def __init__(self, factory: type[SpeakerEmbedder] | None = None) -> None:
        if factory is None:
            factory = FakeEmbedder if os.environ.get("RTFC_DIARIZER") == "fake" else SherpaEmbedder
        self._factory = factory
        self._embedder: SpeakerEmbedder | None = None
        self._failed = False
        self._warmup: asyncio.Task[SpeakerEmbedder | None] | None = None
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diarization")

    async def _ready(self) -> SpeakerEmbedder | None:
        async with self._lock:
            if self._embedder is None and not self._failed:
                try:
                    self._embedder = await asyncio.get_running_loop().run_in_executor(
                        self._executor, self._factory
                    )
                except Exception:
                    log.exception("diarização indisponível (modelo não carregou)")
                    self._failed = True
            return self._embedder

    @property
    def loaded(self) -> bool:
        return self._embedder is not None

    def warm_up(self) -> None:
        """Carrega (e baixa, na primeira vez) o modelo em segundo plano."""
        if self._embedder is None and not self._failed and self._warmup is None:
            self._warmup = asyncio.get_running_loop().create_task(self._ready())
            self._warmup.add_done_callback(lambda _: setattr(self, "_warmup", None))

    async def embed(self, audio: Vector) -> Vector | None:
        embedder = await self._ready()
        if embedder is None:
            return None
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, embedder.embed, audio
        )

    async def embed_many(self, chunks: list[Vector]) -> list[Vector | None]:
        embedder = await self._ready()
        if embedder is None:
            return [None] * len(chunks)
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, lambda: [embedder.embed(c) for c in chunks]
        )

    async def unload(self) -> None:
        async with self._lock:
            self._embedder = None
            self._failed = False

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._executor.shutdown(wait=False, cancel_futures=True)
