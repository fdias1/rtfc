"""Modelo de embedding de falante (sherpa-onnx), baixado sob demanda do GitHub do projeto."""

import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

EMBEDDING_MODEL = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
"""3D-Speaker ERes2Net base (Apache-2.0, ~40 MB). Escolhido no ADR 0008."""
EMBEDDING_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
    + EMBEDDING_MODEL
)

ProgressFn = Callable[[int, int], None]


def models_dir() -> Path:
    base = os.environ.get("RTFC_MODELS_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "rtfc" / "models"
    return root / "diarization"


def embedding_path() -> Path:
    return models_dir() / EMBEDDING_MODEL


def download_embedding(on_progress: ProgressFn | None = None) -> Path:
    """Baixa o modelo se ainda não estiver no cache. Bloqueante."""
    path = embedding_path()
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with urllib.request.urlopen(EMBEDDING_URL, timeout=60) as resp, tmp.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 16):
            out.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)
    tmp.replace(path)
    return path
