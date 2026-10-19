"""Transcrição local (Whisper). Ver ADR 0003 para o motor/modelo padrão por plataforma."""

import os
import platform
import sys

from rtfc.stt.base import MODEL_SIZES, AudioArray, STTEngine, Transcription, Word
from rtfc.stt.faster import FasterWhisperEngine
from rtfc.stt.mlx import MlxWhisperEngine, mlx_available


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def default_engine_name() -> str:
    return "mlx-whisper" if is_apple_silicon() and mlx_available() else "faster-whisper"


def default_model(engine: str) -> str:
    return "large-v3-turbo" if engine == "mlx-whisper" else "small"


def create_engine(engine: str | None = None, model: str | None = None) -> STTEngine:
    """Cria o motor pedido, ou o padrão da plataforma (sobrescrevível por RTFC_STT_ENGINE/MODEL)."""
    engine = engine or os.environ.get("RTFC_STT_ENGINE") or default_engine_name()
    model = model or os.environ.get("RTFC_STT_MODEL") or default_model(engine)
    if engine == "mlx-whisper":
        return MlxWhisperEngine(model)
    if engine == "faster-whisper":
        return FasterWhisperEngine(model)
    raise ValueError(f"motor de STT desconhecido: {engine}")


__all__ = [
    "MODEL_SIZES",
    "AudioArray",
    "FasterWhisperEngine",
    "MlxWhisperEngine",
    "STTEngine",
    "Transcription",
    "Word",
    "create_engine",
    "default_engine_name",
    "default_model",
]
