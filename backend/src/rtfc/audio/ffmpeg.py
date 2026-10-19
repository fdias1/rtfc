"""Localiza o ffmpeg/ffprobe e monta as linhas de comando usadas pelo backend."""

import asyncio
import json
import os
import shutil
from functools import cache
from pathlib import Path

from rtfc.audio import PIPELINE_SAMPLE_RATE


class FfmpegNotFoundError(RuntimeError):
    pass


@cache
def ffmpeg_path() -> str:
    return _find("RTFC_FFMPEG", "ffmpeg")


@cache
def ffprobe_path() -> str:
    return _find("RTFC_FFPROBE", "ffprobe")


def _find(env: str, name: str) -> str:
    override = os.environ.get(env)
    if override:
        return override
    found = shutil.which(name)
    if not found:
        raise FfmpegNotFoundError(f"{name} não encontrado no PATH (defina {env})")
    return found


def live_recorder_args(input_rate: int, ogg_path: Path) -> list[str]:
    """PCM s16le mono no stdin → `ogg_path` (Opus) + PCM 16 kHz no stdout."""
    return [
        ffmpeg_path(),
        # Sem -nostdin: o PCM chega justamente pelo stdin.
        *("-hide_banner", "-loglevel", "error", "-y"),
        *("-f", "s16le", "-ar", str(input_rate), "-ac", "1", "-i", "pipe:0"),
        # Saída 1: gravação. Páginas curtas para perder pouco num encerramento forçado.
        *("-map", "0:a", "-c:a", "libopus", "-b:a", "48k", "-application", "audio"),
        *("-page_duration", "500000", "-flush_packets", "1", "-f", "ogg", str(ogg_path)),
        # Saída 2: pipeline.
        *("-map", "0:a", "-f", "s16le", "-ar", str(PIPELINE_SAMPLE_RATE), "-ac", "1", "pipe:1"),
    ]


def file_decoder_args(path: Path) -> list[str]:
    """Qualquer áudio/vídeo → PCM 16 kHz mono no stdout."""
    return [
        ffmpeg_path(),
        *("-hide_banner", "-loglevel", "error", "-nostdin"),
        *("-i", str(path), "-vn", "-map", "0:a:0"),
        *("-f", "s16le", "-ar", str(PIPELINE_SAMPLE_RATE), "-ac", "1", "pipe:1"),
    ]


def system_audio_capture_args() -> list[str]:
    """Captura do áudio do sistema pelo backend (fallback do Linux: monitor do PulseAudio/PipeWire).

    Ainda não validado em hardware (spike do M1); ver ADR 0002.
    """
    return [
        ffmpeg_path(),
        *("-hide_banner", "-loglevel", "error", "-nostdin"),
        *("-f", "pulse", "-i", "@DEFAULT_MONITOR@"),
        *("-f", "s16le", "-ar", "48000", "-ac", "1", "pipe:1"),
    ]


class MediaInfo:
    def __init__(self, duration_ms: int | None, has_video: bool, has_audio: bool) -> None:
        self.duration_ms = duration_ms
        self.has_video = has_video
        self.has_audio = has_audio


async def probe(path: Path) -> MediaInfo:
    proc = await asyncio.create_subprocess_exec(
        ffprobe_path(),
        *("-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise ValueError(err.decode(errors="replace").strip() or "arquivo de mídia inválido")
    data = json.loads(out)
    streams = data.get("streams", [])
    kinds = {s.get("codec_type") for s in streams}
    # Imagens de capa (mp3 com arte) aparecem como vídeo "attached_pic": não contam.
    has_video = any(
        s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        for s in streams
    )
    duration = data.get("format", {}).get("duration")
    duration_ms = round(float(duration) * 1000) if duration else None
    return MediaInfo(duration_ms, has_video=has_video, has_audio="audio" in kinds)
