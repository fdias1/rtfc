"""Motor faster-whisper (CTranslate2): CPU em qualquer SO e CUDA quando houver GPU NVIDIA."""

import os
from typing import Any

from rtfc.stt.base import AudioArray, Transcription, Word


class FasterWhisperEngine:
    name = "faster-whisper"

    def __init__(
        self,
        model: str = "small",
        *,
        device: str = "auto",
        compute_type: str = "default",
        beam_size: int = 1,
        download_root: str | None = None,
    ) -> None:
        self.model = model
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._download_root = download_root or os.environ.get("RTFC_MODELS_DIR")
        self._impl: Any = None

    def load(self) -> None:
        if self._impl is not None:
            return
        from faster_whisper import WhisperModel

        compute = self._compute_type
        if compute == "default":
            # int8 na CPU é o melhor custo/benefício; na GPU, float16.
            compute = "int8" if self._device in ("auto", "cpu") else "float16"
        self._impl = WhisperModel(
            self.model,
            device=self._device,
            compute_type=compute,
            cpu_threads=max(1, (os.cpu_count() or 4) - 2),
            download_root=self._download_root,
        )

    def transcribe(
        self, audio: AudioArray, *, language: str | None = None, prompt: str | None = None
    ) -> Transcription:
        self.load()
        segments, info = self._impl.transcribe(
            audio,
            language=language,
            initial_prompt=prompt or None,
            beam_size=self._beam_size,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,
            without_timestamps=False,
        )
        words: list[Word] = []
        for seg in segments:  # gerador: a transcrição acontece aqui
            for w in seg.words or []:
                words.append(Word(w.word, float(w.start), float(w.end), float(w.probability)))
        return Transcription(words, info.language, float(info.language_probability))
