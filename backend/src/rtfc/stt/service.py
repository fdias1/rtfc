"""Serviço de STT do processo: um motor carregado uma vez, uma thread de inferência.

As sessões chamam `transcribe()` (async); a inferência roda numa única thread dedicada, então
duas sessões simultâneas se revezam no modelo em vez de disputar a GPU/CPU.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from rtfc.stt import create_engine
from rtfc.stt.base import AudioArray, STTEngine, Transcription
from rtfc.stt.models import download, repo_for

log = logging.getLogger(__name__)

SttState = Literal["idle", "downloading", "loading", "ready", "error"]


@dataclass(frozen=True)
class SttStatus:
    state: SttState
    engine: str
    model: str
    progress: float | None = None
    message: str | None = None


StatusListener = Callable[[SttStatus], Awaitable[None]]


class SttService:
    def __init__(
        self,
        engine_factory: Callable[[], STTEngine] = create_engine,
        *,
        download_models: bool = True,
    ) -> None:
        self._factory = engine_factory
        self._download = download_models
        self._engine: STTEngine | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._ready_lock = asyncio.Lock()
        self._listeners: set[StatusListener] = set()
        self.status = SttStatus("idle", "?", "?")

    def subscribe(self, listener: StatusListener) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    async def _set_status(self, status: SttStatus) -> None:
        self.status = status
        for listener in list(self._listeners):
            with contextlib.suppress(Exception):
                await listener(status)

    async def ensure_ready(self) -> STTEngine:
        async with self._ready_lock:
            if self._engine is not None:
                return self._engine
            loop = asyncio.get_running_loop()
            engine = self._factory()
            name, model = engine.name, engine.model
            try:
                if self._download:
                    last = 0.0

                    def on_progress(done: int, total: int) -> None:
                        nonlocal last
                        now = time.monotonic()
                        if now - last < 0.5 and done < total:
                            return
                        last = now
                        frac = done / total if total else None
                        asyncio.run_coroutine_threadsafe(
                            self._set_status(SttStatus("downloading", name, model, frac)), loop
                        )

                    await self._set_status(SttStatus("downloading", name, model, 0.0))
                    await loop.run_in_executor(
                        self._executor, download, repo_for(name, model), on_progress
                    )
                await self._set_status(SttStatus("loading", name, model))
                t0 = time.perf_counter()
                await loop.run_in_executor(self._executor, engine.load)
                log.info("STT %s/%s carregado em %.1fs", name, model, time.perf_counter() - t0)
            except Exception as exc:
                log.exception("falha ao preparar o STT")
                await self._set_status(SttStatus("error", name, model, message=str(exc)))
                raise
            self._engine = engine
            await self._set_status(SttStatus("ready", name, model))
            return engine

    async def transcribe(
        self, audio: AudioArray, *, language: str | None, prompt: str | None
    ) -> Transcription:
        engine = await self.ensure_ready()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, lambda: engine.transcribe(audio, language=language, prompt=prompt)
        )

    async def run_blocking[T](self, fn: Callable[[], T]) -> T:
        """Roda outra tarefa pesada (VAD de arquivo inteiro) fora do event loop."""
        return await asyncio.get_running_loop().run_in_executor(None, fn)
