"""Fontes de áudio do backend, todas entregando PCM 16 kHz a um `sink`.

- `LiveRecorder`: recebe PCM 48 kHz (da UI ou da captura do backend), grava `audio.ogg`
  e repassa 16 kHz ao sink.
- `FileDecoder`: decodifica um arquivo de áudio/vídeo para 16 kHz.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from rtfc.audio import BYTES_PER_SAMPLE, PIPELINE_SAMPLE_RATE
from rtfc.audio.ffmpeg import file_decoder_args, live_recorder_args, system_audio_capture_args

log = logging.getLogger(__name__)

PcmSink = Callable[[bytes], None]
ProgressCallback = Callable[[int], Awaitable[None]]
"""Recebe os milissegundos de áudio já processados."""

READ_CHUNK = 3200  # 100 ms a 16 kHz
STOP_TIMEOUT_S = 5.0


class AudioSourceError(RuntimeError):
    pass


async def _pump_stdout(proc: asyncio.subprocess.Process, sink: PcmSink) -> int:
    """Lê PCM 16 kHz do stdout do ffmpeg até o EOF. Devolve o total de amostras."""
    assert proc.stdout is not None
    total = 0
    while chunk := await proc.stdout.read(READ_CHUNK):
        sink(chunk)
        total += len(chunk)
    return total // BYTES_PER_SAMPLE


async def _stderr_text(proc: asyncio.subprocess.Process) -> str:
    if proc.stderr is None:
        return ""
    return (await proc.stderr.read()).decode(errors="replace").strip()


class LiveRecorder:
    """Uma sessão ao vivo: PCM s16le mono `input_rate` → `audio.ogg` + 16 kHz para o sink."""

    def __init__(self, ogg_path: Path, sink: PcmSink, input_rate: int = 48_000) -> None:
        self.ogg_path = ogg_path
        self.input_rate = input_rate
        self._sink = sink
        self._proc: asyncio.subprocess.Process | None = None
        self._pump: asyncio.Task[int] | None = None
        self._capture: asyncio.subprocess.Process | None = None
        self._capture_task: asyncio.Task[None] | None = None
        self.samples_in = 0

    @property
    def duration_ms(self) -> int:
        return self.samples_in * 1000 // self.input_rate

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *live_recorder_args(self.input_rate, self.ogg_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._pump = asyncio.create_task(_pump_stdout(self._proc, self._sink))

    async def start_backend_capture(self) -> None:
        """Usa o ffmpeg do backend para capturar o áudio do sistema (Linux)."""
        await self.start()
        self._capture = await asyncio.create_subprocess_exec(
            *system_audio_capture_args(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._capture_task = asyncio.create_task(self._forward_capture())

    async def _forward_capture(self) -> None:
        assert self._capture is not None and self._capture.stdout is not None
        while chunk := await self._capture.stdout.read(9600):
            await self.write(chunk)

    async def write(self, pcm: bytes) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdin.is_closing():
            raise AudioSourceError("gravação não está ativa")
        proc.stdin.write(pcm)
        self.samples_in += len(pcm) // BYTES_PER_SAMPLE
        try:
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise AudioSourceError(f"ffmpeg encerrou: {await _stderr_text(proc)}") from exc

    async def stop(self) -> None:
        """Fecha o stdin (o ffmpeg finaliza o .ogg) e espera o fim do pipeline."""
        if self._capture is not None:
            with contextlib.suppress(ProcessLookupError):
                self._capture.terminate()
            if self._capture_task is not None:
                with contextlib.suppress(Exception):
                    await self._capture_task
        proc = self._proc
        if proc is None:
            return
        if proc.stdin is not None and not proc.stdin.is_closing():
            proc.stdin.close()
        try:
            if self._pump is not None:
                await asyncio.wait_for(self._pump, STOP_TIMEOUT_S)
            await asyncio.wait_for(proc.wait(), STOP_TIMEOUT_S)
        except TimeoutError:
            log.warning("ffmpeg não terminou a tempo; matando")
            proc.kill()
            await proc.wait()


class FileDecoder:
    """Decodifica um arquivo para 16 kHz, mais rápido que o tempo real, reportando progresso."""

    def __init__(self, path: Path, sink: PcmSink, on_progress: ProgressCallback) -> None:
        self.path = path
        self._sink = sink
        self._on_progress = on_progress
        self._proc: asyncio.subprocess.Process | None = None
        self.samples = 0

    async def run(self) -> int:
        """Decodifica até o fim. Devolve a duração em ms. Cancelável."""
        self._proc = await asyncio.create_subprocess_exec(
            *file_decoder_args(self.path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        proc = self._proc
        assert proc.stdout is not None
        last_report = 0
        try:
            while chunk := await proc.stdout.read(READ_CHUNK * 10):
                self._sink(chunk)
                self.samples += len(chunk) // BYTES_PER_SAMPLE
                ms = self.samples * 1000 // PIPELINE_SAMPLE_RATE
                if ms - last_report >= 1000:
                    last_report = ms
                    await self._on_progress(ms)
            code = await proc.wait()
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            raise
        if code != 0:
            raise AudioSourceError(await _stderr_text(proc) or f"ffmpeg saiu com código {code}")
        ms = self.samples * 1000 // PIPELINE_SAMPLE_RATE
        await self._on_progress(ms)
        return ms
