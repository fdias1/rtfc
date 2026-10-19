"""Motor MLX Whisper: GPU (Metal) do Apple Silicon. Só existe em macOS arm64 (extra `mlx`)."""

import threading
from typing import Any

from rtfc.stt.base import AudioArray, Transcription, Word

MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


def mlx_available() -> bool:
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return False
    return True


class MlxWhisperEngine:
    name = "mlx-whisper"

    def __init__(self, model: str = "large-v3-turbo") -> None:
        self.model = model
        self._repo = MLX_REPOS.get(model, model)
        self._mlx: Any = None
        # O MLX mantém o modelo num cache global; serializamos as chamadas.
        self._lock = threading.Lock()

    def load(self) -> None:
        if self._mlx is not None:
            return
        import mlx.core as mx
        import mlx_whisper
        from mlx_whisper.load_models import load_model
        from mlx_whisper.transcribe import ModelHolder

        # Baixa e aquece o modelo uma vez (o transcribe() reusa o ModelHolder).
        ModelHolder.get_model(self._repo, mx.float16)
        _ = load_model  # o import garante que o pacote está completo
        self._mlx = mlx_whisper

    def transcribe(
        self, audio: AudioArray, *, language: str | None = None, prompt: str | None = None
    ) -> Transcription:
        self.load()
        with self._lock:
            result: dict[str, Any] = self._mlx.transcribe(
                audio,
                path_or_hf_repo=self._repo,
                language=language,
                initial_prompt=prompt or None,
                word_timestamps=True,
                condition_on_previous_text=False,
                fp16=True,
                verbose=None,
            )
        words = [
            Word(w["word"], float(w["start"]), float(w["end"]), float(w.get("probability", 1.0)))
            for seg in result.get("segments", [])
            for w in seg.get("words", [])
        ]
        return Transcription(words, result.get("language"), None)
